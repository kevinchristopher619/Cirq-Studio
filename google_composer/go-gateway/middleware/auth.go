package middleware

import (
	"context"
	"net/http"
	"os"
	"strings"

	"firebase.google.com/go/v4/auth"
	"github.com/gin-gonic/gin"
)

// FirebaseAuth validates the JWT. It expects the Firebase client to be injected at startup.
func FirebaseAuth(client *auth.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Safe Dev Gate: If client is nil, we MUST be in dev/mock mode
		if client == nil {
			if os.Getenv("ENV") != "development" {
				c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": "Auth client uninitialized in production"})
				return
			}
			c.Set("userID", "local_test_user")
			c.Next()
			return
		}

		authHeader := c.GetHeader("Authorization")

		if authHeader == "" {
			if os.Getenv("ENV") == "development" {
				c.Set("userID", "local_test_user")
				c.Next()
				return
			}
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "Missing Authorization header"})
			return
		}

		// 3. Idiomatic Prefix Trim
		tokenString := strings.TrimPrefix(authHeader, "Bearer ")

		token, err := client.VerifyIDToken(context.Background(), tokenString)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "Invalid or expired token"})
			return
		}

		c.Set("userID", token.UID)
		c.Next()
	}
}
