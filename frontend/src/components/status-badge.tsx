import React from "react";

const STATUS_COLORS: Record<string, string> = {
  open: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  new: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  hunting: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  enriched: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
  validated: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400",
  sent: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-400",
  closed_hired: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  closed_not_hired: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  closed_test: "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300",
  skipped: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  active: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  inactive: "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300",
  pending: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  running: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  completed: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  cancelled: "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300",
  Valid: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  Invalid: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  Unknown: "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300",
};

interface StatusBadgeProps {
  status: string;
  className?: string;
}

export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const colorClass = STATUS_COLORS[status] || "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300";
  const display = status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colorClass} ${className}`}>
      {display}
    </span>
  );
}
