package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/dbos-inc/dbos-transact-golang/dbos"
	"github.com/gin-gonic/gin"
)

func workflow(ctx dbos.DBOSContext, name string) (string, error) {
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

	return "workflow executed", nil
}

func stepOne(ctx context.Context, name string) (int, error) {
	fmt.Printf("Hello %s\n", name)
	fmt.Println("Step one completed!")
	return len(name), nil
}

func stepTwo(ctx context.Context, name string, nameLength int) (string, error) {
	fmt.Printf("Step two completed for %s; the name has %d characters.\n", name, nameLength)
	return "ok", nil
}

func main() {
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

	router := gin.Default()
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
