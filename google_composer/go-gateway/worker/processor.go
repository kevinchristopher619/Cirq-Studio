package worker

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"

	"quantum-gateway/models"

	"cloud.google.com/go/firestore"
	"github.com/hibiken/asynq"
)

const (
	TypeSimulationJob = "simulation:process"
)

// OPTIMIZED: Added Request to the payload to prevent a DB read on the worker side
type SimulationJobPayload struct {
	JobID   string            `json:"job_id"`
	Request models.JobRequest `json:"request"`
}

type Processor struct {
	firestoreClient *firestore.Client
	engineURL       string
}

func NewProcessor(fsClient *firestore.Client) *Processor {
	engineURL := os.Getenv("ENGINE_URL")
	if engineURL == "" {
		engineURL = "http://localhost:5001/run"
	}
	return &Processor{
		firestoreClient: fsClient,
		engineURL:       engineURL,
	}
}

func (p *Processor) ProcessTask(ctx context.Context, t *asynq.Task) error {
	var payload SimulationJobPayload
	if err := json.Unmarshal(t.Payload(), &payload); err != nil {
		return fmt.Errorf("json.Unmarshal failed: %v: %w", err, asynq.SkipRetry)
	}

	log.Printf("Worker processing JobID: %s", payload.JobID)

	// Update status to RUNNING
	_, err := p.firestoreClient.Collection("jobs").Doc(payload.JobID).Update(ctx, []firestore.Update{
		{Path: "status", Value: "RUNNING"},
		{Path: "updated_at", Value: time.Now()},
	})
	if err != nil {
		log.Printf("Failed to update status to RUNNING for job %s: %v", payload.JobID, err)
		return err
	}

	// Make HTTP call to Python engine
	reqBody, _ := json.Marshal(payload.Request)

	// OPTIMIZED: Tie the HTTP request to a timeout context rather than the client itself
	reqCtx, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()

	httpReq, err := http.NewRequestWithContext(reqCtx, "POST", p.engineURL, bytes.NewBuffer(reqBody))
	if err != nil {
		p.failJob(ctx, payload.JobID, fmt.Sprintf("failed to create http request: %v", err))
		return err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	client := &http.Client{} // Default client, timeout handled by context
	resp, err := client.Do(httpReq)
	if err != nil {
		p.failJob(ctx, payload.JobID, fmt.Sprintf("failed to call python engine: %v", err))
		return err
	}
	defer resp.Body.Close()

	bodyBytes, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		errStr := fmt.Sprintf("python engine returned %d: %s", resp.StatusCode, string(bodyBytes))
		p.failJob(ctx, payload.JobID, errStr)
		return fmt.Errorf("%s: %w", errStr, asynq.SkipRetry)
	}

	// Parse JSON result and store back to Firestore
	var result map[string]interface{}
	if err := json.Unmarshal(bodyBytes, &result); err != nil {
		errStr := fmt.Sprintf("could not parse python engine response: %v", err)
		p.failJob(ctx, payload.JobID, errStr)
		return fmt.Errorf("%s: %w", errStr, asynq.SkipRetry)
	}

	// Mark COMPLETED
	_, err = p.firestoreClient.Collection("jobs").Doc(payload.JobID).Update(ctx, []firestore.Update{
		{Path: "status", Value: "COMPLETED"},
		{Path: "result", Value: result},
		{Path: "updated_at", Value: time.Now()},
	})

	if err != nil {
		log.Printf("Failed to update status to COMPLETED for job %s: %v", payload.JobID, err)
		return err
	}

	log.Printf("Successfully completed JobID: %s", payload.JobID)
	return nil
}

func (p *Processor) failJob(ctx context.Context, jobID, errorMsg string) {
	log.Printf("Failing JobID %s: %s", jobID, errorMsg)
	p.firestoreClient.Collection("jobs").Doc(jobID).Update(ctx, []firestore.Update{
		{Path: "status", Value: "FAILED"},
		{Path: "error", Value: errorMsg},
		{Path: "updated_at", Value: time.Now()},
	})
}
