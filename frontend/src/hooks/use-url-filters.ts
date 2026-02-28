"use client";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { useCallback } from "react";

type FilterValue = string | number | boolean | null | undefined;

export function useUrlFilters<T extends Record<string, FilterValue>>(
  defaults: T
): [T, (updates: Partial<T>) => void, () => void] {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  // Read current filters from URL, falling back to defaults
  const filters = {} as T;
  for (const [key, defaultVal] of Object.entries(defaults)) {
    const urlVal = searchParams.get(key);
    if (urlVal === null || urlVal === undefined) {
      (filters as any)[key] = defaultVal;
    } else if (typeof defaultVal === "number") {
      (filters as any)[key] = Number(urlVal) || defaultVal;
    } else if (typeof defaultVal === "boolean") {
      (filters as any)[key] = urlVal === "true";
    } else {
      (filters as any)[key] = urlVal;
    }
  }

  const setFilters = useCallback(
    (updates: Partial<T>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value === null || value === undefined || value === "" || value === defaults[key]) {
          params.delete(key);
        } else {
          params.set(key, String(value));
        }
      }
      // Reset to page 1 when filters change (unless page is being set)
      if (!("page" in updates) && params.has("page")) {
        params.set("page", "1");
      }
      router.push(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [searchParams, router, pathname, defaults]
  );

  const resetFilters = useCallback(() => {
    router.push(pathname, { scroll: false });
  }, [router, pathname]);

  return [filters, setFilters, resetFilters];
}
