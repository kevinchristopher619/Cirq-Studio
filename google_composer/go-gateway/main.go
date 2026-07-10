package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"quantum-gateway/middleware"
	"quantum-gateway/models"
	"quantum-gateway/worker"

	"cloud.google.com/go/firestore"
	firebase "firebase.google.com/go/v4"
	"firebase.google.com/go/v4/auth"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/hibiken/asynq"
	"google.golang.org/api/iterator"
	"google.golang.org/api/option"
)

func initFirebase() (*auth.Client, *firestore.Client) {
	var app *firebase.App
	var err error

	credPath := os.Getenv("FIREBASE_CREDENTIALS")

	if credPath != "" {
		opt := option.WithCredentialsFile(credPath)
		app, err = firebase.NewApp(context.Background(), nil, opt)
	} else {
		if os.Getenv("ENV") != "development" {
			log.Println("WARNING: Running in production without FIREBASE_CREDENTIALS set.")
		}
		app, err = firebase.NewApp(context.Background(), nil)
	}

	if err != nil {
		if os.Getenv("ENV") == "development" {
			log.Printf("Bypassing Firebase App init in development: %v", err)
			return nil, nil
		}
		log.Fatalf("Failed to initialize Firebase app: %v", err)
	}

	authClient, err := app.Auth(context.Background())
	if err != nil {
		if os.Getenv("ENV") == "development" {
			log.Printf("Bypassing Firebase Auth init in development: %v", err)
		} else {
			log.Fatalf("Failed to initialize Firebase Auth Client: %v", err)
		}
	}

	fsClient, err := app.Firestore(context.Background())
	if err != nil {
		if os.Getenv("ENV") == "development" {
			log.Printf("Bypassing Firestore init in development: %v", err)
		} else {
			log.Fatalf("Failed to initialize Firestore Client: %v", err)
		}
	}

	return authClient, fsClient
}

func performGarbageCollection(fsClient *firestore.Client) (int, []string, error) {
	log.Println("Running background garbage collection...")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	// Find all jobs where ExpiresAt is in the past
	now := time.Now()
	iter := fsClient.Collection("jobs").Where("expires_at", "<", now).Documents(ctx)

	deletedCount := 0
	var deletedIds []string
	for {
		doc, err := iter.Next()
		if errors.Is(err, iterator.Done) {
			break // Reached the end of the results
		}
		if err != nil {
			log.Printf("Error iterating during garbage collection: %v", err)
			return deletedCount, deletedIds, err
		}

		// Delete the expired document
		_, err = doc.Ref.Delete(ctx)
		if err == nil {
			deletedCount++
			deletedIds = append(deletedIds, doc.Ref.ID)
			log.Printf("Garbage Collector deleted expired JobID: %s", doc.Ref.ID)
		} else {
			log.Printf("Failed to delete expired JobID %s: %v", doc.Ref.ID, err)
		}
	}
	if deletedCount > 0 {
		log.Printf("Garbage collection complete. Deleted %d old jobs.", deletedCount)
	} else {
		log.Println("Garbage collection complete. No expired jobs found.")
	}
	return deletedCount, deletedIds, nil
}

// startGarbageCollector runs a background loop to delete expired jobs for free
func startGarbageCollector(fsClient *firestore.Client) {
	ticker := time.NewTicker(1 * time.Hour) // Run every hour

	go func() {
		// Run once immediately on startup
		_, _, _ = performGarbageCollection(fsClient)

		for range ticker.C {
			_, _, _ = performGarbageCollection(fsClient)
		}
	}()
}

func main() {
	// 1. Config Loading
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	redisAddr := os.Getenv("REDIS_ADDR")
	if redisAddr == "" {
		redisAddr = "localhost:6379"
	}

	// 2. Dependency Injection
	authClient, fsClient := initFirebase()

	// Initialize Asynq Client
	redisOpt := asynq.RedisClientOpt{Addr: redisAddr}
	asynqClient := asynq.NewClient(redisOpt)
	defer asynqClient.Close()

	// Initialize Asynq Server
	asynqSrv := asynq.NewServer(
		redisOpt,
		asynq.Config{
			Concurrency: 10,
			Queues: map[string]int{
				"default": 1,
			},
		},
	)

	// Start worker & Background services if we have a valid firestore connection
	if fsClient != nil {
		// Start free garbage collector
		startGarbageCollector(fsClient)

		// Start Asynq worker
		mux := asynq.NewServeMux()
		processor := worker.NewProcessor(fsClient)
		mux.HandleFunc(worker.TypeSimulationJob, processor.ProcessTask)

		go func() {
			log.Printf("Starting asynq worker on redis %s...", redisAddr)
			if err := asynqSrv.Run(mux); err != nil {
				log.Fatalf("Asynq worker failed: %v", err)
			}
		}()
	}

	// 3. Setup Router
	r := gin.Default()

	// Enable CORS for local development
	r.Use(func(c *gin.Context) {
		c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
		c.Writer.Header().Set("Access-Control-Allow-Credentials", "true")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Content-Length, Accept-Encoding, X-CSRF-Token, Authorization, accept, origin, Cache-Control, X-Requested-With")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS, GET, PUT, DELETE")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}

		c.Next()
	})

	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "Gateway Active"})
	})

	r.GET("/api/gc", func(c *gin.Context) {
		if fsClient == nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Firestore not connected"})
			return
		}
		deletedCount, deletedIds, err := performGarbageCollection(fsClient)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{
				"error":         err.Error(),
				"deleted_count": deletedCount,
				"deleted_ids":   deletedIds,
			})
			return
		}
		c.JSON(http.StatusOK, gin.H{
			"status":        "success",
			"deleted_count": deletedCount,
			"deleted_ids":   deletedIds,
		})
	})

	api := r.Group("/api")
	api.Use(middleware.FirebaseAuth(authClient))
	{
		api.POST("/jobs", func(c *gin.Context) {
			var req models.JobRequest
			if err := c.ShouldBindJSON(&req); err != nil {
				c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
				return
			}

			userID, _ := c.Get("userID")

			jobID := uuid.New().String()

			// Updated to use time.Time and a 24-hour Expiry
			record := models.JobRecord{
				JobID:     jobID,
				UserID:    userID.(string),
				Status:    "QUEUED",
				Request:   req,
				CreatedAt: time.Now(),
				UpdatedAt: time.Now(),
				ExpiresAt: time.Now().Add(24 * time.Hour),
			}

			// Save to Firestore First
			if fsClient != nil {
				_, err := fsClient.Collection("jobs").Doc(jobID).Set(context.Background(), record)
				if err != nil {
					c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to save job to database"})
					return
				}
			}

			// Enqueue Task to Redis with the full request payload
			payload, _ := json.Marshal(worker.SimulationJobPayload{
				JobID:   jobID,
				Request: req,
			})
			task := asynq.NewTask(worker.TypeSimulationJob, payload)

			if _, err := asynqClient.Enqueue(task); err != nil {
				if fsClient != nil {
					fsClient.Collection("jobs").Doc(jobID).Update(context.Background(), []firestore.Update{
						{Path: "status", Value: "FAILED"},
						{Path: "error", Value: "Failed to enqueue task"},
					})
				}
				log.Printf("Failed to enqueue task: %v", err)
				c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to queue job for processing"})
				return
			}

			c.JSON(http.StatusAccepted, gin.H{
				"message": "Job accepted",
				"job_id":  jobID,
				"user_id": userID,
				"target":  req.Target,
			})
		})

		api.GET("/jobs/:id", func(c *gin.Context) {
			jobID := c.Param("id")

			if fsClient == nil {
				c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Firestore not connected via dev mode"})
				return
			}

			docSnap, err := fsClient.Collection("jobs").Doc(jobID).Get(context.Background())
			if err != nil {
				c.JSON(http.StatusNotFound, gin.H{"error": "Job not found"})
				return
			}

			var record models.JobRecord
			if err := docSnap.DataTo(&record); err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to decode job"})
				return
			}

			userID, _ := c.Get("userID")
			if record.UserID != userID.(string) {
				c.JSON(http.StatusForbidden, gin.H{"error": "Access denied"})
				return
			}

			c.JSON(http.StatusOK, record)
		})
	}

	// 4. Graceful Shutdown Setup
	srv := &http.Server{
		Addr:    ":" + port,
		Handler: r,
	}

	go func() {
		log.Printf("Starting server on port %s (ENV: %s)", port, os.Getenv("ENV"))
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("Listen error: %s\n", err)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("Interrupt signal received. Shutting down server...")

	asynqSrv.Shutdown()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Fatal("Server forced to shutdown:", err)
	}

	if fsClient != nil {
		fsClient.Close()
	}

	log.Println("Server exiting gracefully.")
}
