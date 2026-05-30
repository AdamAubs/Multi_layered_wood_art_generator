package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/joho/godotenv"
)

type config struct {
	JobsRoot string
	PythonPath string
	MaxWorkers int
	JobTimeoutSec int
	APIAddr string
}

func main() {
	if err := godotenv.Load(); err != nil {
		log.Printf("no .env loaded: %v", err)
	}

	cfg, err := loadConfig()
	if err != nil {
		fmt.Fprintln(os.Stderr, "config error:", err)
		os.Exit(1)
	}

	mux := http.NewServeMux()

	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(([]byte("ok\n")))
	})

	server := &http.Server{
		Addr:  cfg.APIAddr,
		Handler: mux,
		ReadTimeout: 10 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout: 60 * time.Second,	
	}

	fmt.Printf("server starting on %s\n", cfg.APIAddr)
	fmt.Printf("JOBS_ROOT=%s\n", cfg.JobsRoot)
	fmt.Printf("PYTHON_PATH=%s\n", cfg.PythonPath)
	fmt.Printf("MAX_WORKERS=%d\n", cfg.MaxWorkers)
	fmt.Printf("JOB_TIMEOUT_SEC=%d\n", cfg.JobTimeoutSec)

	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}

func loadConfig() (config, error) {
	cfg := config{
		JobsRoot: os.Getenv("JOBS_ROOT"),
		PythonPath: os.Getenv("PYTHON_PATH"),
		APIAddr: getenvDefault("API_ADDR", ":8080"),
		MaxWorkers: 2,
		JobTimeoutSec: 3600,
	}

	if v := os.Getenv("MAX_WORKERS"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n <= 0 {
			return config{}, fmt.Errorf("MAX_WORKERS must be a positive integer")
		}
		cfg.MaxWorkers = n
	}

	if v := os.Getenv("JOB_TIMEOUT_SEC"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n <= 0 {
			return config{}, fmt.Errorf("JOB_TIMEOUT_SEC must be a positive integer")
		}
		cfg.JobTimeoutSec = n
	}

	if cfg.JobsRoot == "" {
		return config{}, fmt.Errorf("JOBS_ROOT is required")
	}
	if cfg.PythonPath == "" {
		return config{}, fmt.Errorf("PYTHON_PATH is required")
	}

	return cfg, nil
}

func getenvDefault(key, fallback string) string {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	return value
}