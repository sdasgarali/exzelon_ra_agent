"use client";
import React, { useState } from "react";
import { ChevronUp, ChevronDown } from "lucide-react";

export interface Column<T> {
  key: string;
  header: string;
  render?: (item: T) => React.ReactNode;
  sortable?: boolean;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyField: string;
  selectable?: boolean;
  selectedIds?: Set<number | string>;
  onSelectionChange?: (ids: Set<number | string>) => void;
  sortBy?: string;
  sortOrder?: "asc" | "desc";
  onSort?: (column: string, order: "asc" | "desc") => void;
  emptyMessage?: string;
  rowClassName?: (item: T) => string;
}

export function DataTable<T extends Record<string, any>>({
  columns,
  data,
  keyField,
  selectable = false,
  selectedIds = new Set(),
  onSelectionChange,
  sortBy,
  sortOrder = "desc",
  onSort,
  emptyMessage = "No data found",
  rowClassName,
}: DataTableProps<T>) {
  const allSelected = data.length > 0 && data.every((item) => selectedIds.has(item[keyField]));

  const toggleAll = () => {
    if (!onSelectionChange) return;
    if (allSelected) {
      onSelectionChange(new Set());
    } else {
      onSelectionChange(new Set(data.map((item) => item[keyField])));
    }
  };

  const toggleOne = (id: number | string) => {
    if (!onSelectionChange) return;
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    onSelectionChange(next);
  };

  const handleSort = (column: string) => {
    if (!onSort) return;
    const newOrder = sortBy === column && sortOrder === "asc" ? "desc" : "asc";
    onSort(column, newOrder);
  };

  if (data.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500 dark:text-gray-400">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead className="bg-gray-50 dark:bg-gray-800">
          <tr>
            {selectable && (
              <th className="w-10 px-3 py-3">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  className="rounded border-gray-300 dark:border-gray-600"
                />
              </th>
            )}
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider ${
                  col.sortable ? "cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200" : ""
                } ${col.className || ""}`}
                onClick={() => col.sortable && handleSort(col.key)}
              >
                <div className="flex items-center gap-1">
                  {col.header}
                  {col.sortable && sortBy === col.key && (
                    sortOrder === "asc" ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
          {data.map((item) => (
            <tr
              key={item[keyField]}
              className={`hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors ${
                selectedIds.has(item[keyField]) ? "bg-blue-50 dark:bg-blue-900/20" : ""
              } ${rowClassName ? rowClassName(item) : ""}`}
            >
              {selectable && (
                <td className="w-10 px-3 py-3">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(item[keyField])}
                    onChange={() => toggleOne(item[keyField])}
                    className="rounded border-gray-300 dark:border-gray-600"
                  />
                </td>
              )}
              {columns.map((col) => (
                <td key={col.key} className={`px-4 py-3 text-sm text-gray-700 dark:text-gray-300 ${col.className || ""}`}>
                  {col.render ? col.render(item) : item[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
