package models

import "time"

type NoiseConfig struct {
	Type     string  `json:"type" firestore:"type"`
	P        float64 `json:"p" firestore:"p"`
	ReadoutP float64 `json:"readout_p" firestore:"readout_p"`
}

type JobRequest struct {
	Circuit           string       `json:"circuit" binding:"required" firestore:"circuit"`
	Target            string       `json:"target" binding:"required" firestore:"target"`
	SimulationType    string       `json:"simulation_type" firestore:"simulation_type"`
	NoiseConfig       *NoiseConfig `json:"noise_config,omitempty" firestore:"noise_config,omitempty"`
	Repetitions       int          `json:"repetitions" firestore:"repetitions"`
	ReturnStateVector bool         `json:"return_state_vector" firestore:"return_state_vector"`
}

type JobRecord struct {
	JobID     string      `json:"job_id" firestore:"job_id"`
	UserID    string      `json:"user_id" firestore:"user_id"`
	Status    string      `json:"status" firestore:"status"`
	Request   JobRequest  `json:"request" firestore:"request"`
	Result    interface{} `json:"result,omitempty" firestore:"result,omitempty"`
	Error     string      `json:"error,omitempty" firestore:"error,omitempty"`
	CreatedAt time.Time   `json:"created_at" firestore:"created_at"`
	UpdatedAt time.Time   `json:"updated_at" firestore:"updated_at"`
	ExpiresAt time.Time   `json:"expires_at" firestore:"expires_at"`
}
