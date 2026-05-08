package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/dbos-inc/dbos-transact-golang/dbos"
	"github.com/gin-gonic/gin"
)

var logger = slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

type WorkflowInput struct {
	Name    string         `json:"name"`
	Aliases []string       `json:"aliases"`
	Weights map[string]int `json:"weights"`
}

type StepOneResult struct {
	Greeting   string         `json:"greeting"`
	NameLength int            `json:"nameLength"`
	Metrics    map[string]int `json:"metrics"`
}

func envFlag(name string, defaultValue bool) bool {
	raw, ok := os.LookupEnv(name)
	if !ok {
		return defaultValue
	}
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func configureLogging() (string, bool) {
	levelName := strings.ToLower(strings.TrimSpace(os.Getenv("APP_LOG_LEVEL")))
	if levelName == "" {
		levelName = "info"
	}

	level := slog.LevelWarn
	switch levelName {
	case "debug":
		level = slog.LevelDebug
	case "info":
		level = slog.LevelInfo
	case "error":
		level = slog.LevelError
	}

	logger = slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: level}))
	return levelName, envFlag("APP_ACCESS_LOG", false)
}

func workflow(ctx dbos.DBOSContext, input WorkflowInput) (string, error) {
	logger.Info("starting workflow", "name", input.Name)
	stepOneResultAny, err := dbos.RunAsStep(ctx, func(stepCtx context.Context) (any, error) {
		return stepOne(stepCtx, input)
	})
	if err != nil {
		return "", err
	}

	stepOneResult, ok := stepOneResultAny.(StepOneResult)
	if !ok {
		return "", fmt.Errorf("unexpected stepOne result type %T", stepOneResultAny)
	}

	existingFile := filepath.Join(".", "existing.txt")
	if _, statErr := os.Stat(existingFile); os.IsNotExist(statErr) {
		logger.Warn("existing.txt missing; creating it and exiting to simulate a crash")
		file, createErr := os.Create(existingFile)
		if createErr != nil {
			return "", createErr
		}
		if closeErr := file.Close(); closeErr != nil {
			return "", closeErr
		}
		os.Exit(1)
	}

	_, err = dbos.RunAsStep(ctx, func(stepCtx context.Context) (any, error) {
		return stepTwo(stepCtx, input, stepOneResult)
	})
	if err != nil {
		return "", err
	}

	logger.Info("completed workflow", "name", input.Name)
	return "workflow executed", nil
}

func stepOne(ctx context.Context, input WorkflowInput) (StepOneResult, error) {
	logger.Info("hello", "name", input.Name)
	logger.Info("step one completed")
	return StepOneResult{
		Greeting:   fmt.Sprintf("Hello %s", input.Name),
		NameLength: len(input.Name),
		Metrics: map[string]int{
			"nameLength": len(input.Name),
			"aliasCount": len(input.Aliases),
			"weightCount": len(input.Weights),
		},
	}, nil
}

func stepTwo(ctx context.Context, input WorkflowInput, result StepOneResult) (string, error) {
	logger.Info("step two completed", "name", input.Name, "name_length", result.NameLength)
	return "ok", nil
}

func buildWorkflowInput(name string) WorkflowInput {
	return WorkflowInput{
		Name:    name,
		Aliases: []string{strings.ToUpper(name), reverseString(name)},
		Weights: map[string]int{"primary": len(name), "secondary": max(1, len(name)/2)},
	}
}

func reverseString(value string) string {
	runes := []rune(value)
	for left, right := 0, len(runes)-1; left < right; left, right = left+1, right-1 {
		runes[left], runes[right] = runes[right], runes[left]
	}
	return string(runes)
}

func max(a int, b int) int {
	if a > b {
		return a
	}
	return b
}

func main() {
	_, accessLog := configureLogging()
	appName := os.Getenv("DBOS_APP_NAME")
	if appName == "" {
		appName = "dbos-starter"
	}
	dbosContext, err := dbos.NewDBOSContext(context.Background(), dbos.Config{
		AppName:         appName,
		DatabaseURL:     os.Getenv("DBOS_SYSTEM_DATABASE_URL"),
		ConductorAPIKey: os.Getenv("DBOS_CONDUCTOR_KEY"),
		ConductorURL:    os.Getenv("DBOS_CONDUCTOR_URL"),
	})
	if err != nil {
		panic(fmt.Sprintf("initializing DBOS failed: %v", err))
	}

	dbos.RegisterWorkflow(dbosContext, workflow)

	if err := dbos.Launch(dbosContext); err != nil {
		panic(fmt.Sprintf("launching DBOS failed: %v", err))
	}
	defer dbos.Shutdown(dbosContext, 5*time.Second)

	gin.SetMode(gin.ReleaseMode)
	router := gin.New()
	router.Use(gin.Recovery())
	if accessLog {
		router.Use(gin.Logger())
	}
	router.GET("/", func(c *gin.Context) {
		name := c.DefaultQuery("name", "world")
		input := buildWorkflowInput(name)

		handle, runErr := dbos.RunWorkflow(dbosContext, workflow, input)
		if runErr != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": runErr.Error()})
			return
		}

		result, resultErr := handle.GetResult()
		if resultErr != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": resultErr.Error()})
			return
		}

		c.String(http.StatusOK, result)
	})

	if err := router.Run(":8000"); err != nil {
		panic(fmt.Sprintf("starting server failed: %v", err))
	}
}
