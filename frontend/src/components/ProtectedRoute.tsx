"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated, getPayload } from "@/lib/auth";

interface Props {
  requiredRole?: string | string[];
  children: React.ReactNode;
}

export default function ProtectedRoute({ requiredRole, children }: Props) {
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    if (requiredRole) {
      const userRole = getPayload()?.role;
      const allowed = Array.isArray(requiredRole)
        ? requiredRole.includes(userRole ?? "")
        : userRole === requiredRole;
      if (!allowed) {
        router.replace("/403");
      }
    }
  }, [requiredRole, router]);

  return <>{children}</>;
}
