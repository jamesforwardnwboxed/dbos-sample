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

func workflow(ctx dbos.DBOSContext, name string) (string, error) {
	logger.Info("starting workflow", "name", name)
	nameLengthAny, err := dbos.RunAsStep(ctx, func(stepCtx context.Context) (any, error) {
		return stepOne(stepCtx, name)
	})
	if err != nil {
		return "", err
	}

	nameLength, ok := nameLengthAny.(int)
	if !ok {
		return "", fmt.Errorf("unexpected stepOne result type %T", nameLengthAny)
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
		return stepTwo(stepCtx, name, nameLength)
	})
	if err != nil {
		return "", err
	}

	logger.Info("completed workflow", "name", name)
	return "workflow executed", nil
}

func stepOne(ctx context.Context, name string) (int, error) {
	logger.Info("hello", "name", name)
	logger.Info("step one completed")
	return len(name), nil
}

func stepTwo(ctx context.Context, name string, nameLength int) (string, error) {
	logger.Info("step two completed", "name", name, "name_length", nameLength)
	return "ok", nil
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

		handle, runErr := dbos.RunWorkflow(dbosContext, workflow, name)
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
