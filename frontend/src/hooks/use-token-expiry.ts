"use client";
import { useEffect, useRef } from "react";

function decodeJwtPayload(token: string): Record<string, any> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

export function useTokenExpiry(onExpiringSoon?: () => void) {
  const timerRef = useRef<NodeJS.Timeout>();

  useEffect(() => {
    const checkToken = () => {
      const token = localStorage.getItem("token");
      if (!token) return;

      const payload = decodeJwtPayload(token);
      if (!payload?.exp) return;

      const expiresAt = payload.exp * 1000; // Convert to ms
      const now = Date.now();
      const timeLeft = expiresAt - now;
      const oneHour = 60 * 60 * 1000;

      if (timeLeft <= 0) {
        // Token expired - redirect to login
        localStorage.removeItem("token");
        window.location.href = "/login";
      } else if (timeLeft <= oneHour) {
        // Expiring soon - notify
        onExpiringSoon?.();
      }
    };

    // Check immediately
    checkToken();

    // Check every 5 minutes
    timerRef.current = setInterval(checkToken, 5 * 60 * 1000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [onExpiringSoon]);
}
