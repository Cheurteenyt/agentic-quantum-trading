import { useState } from "react"

interface Column<T> {
  key: keyof T | string
  label: string
  width?: string | number
  align?: "left" | "center" | "right"
  render?: (value: any, row: T) => React.ReactNode
}

interface DataTableProps<T> {
  data: T[]
  columns: Column<T>[]
  title?: string
  filters?: { key: string; label: string }[]
  activeFilter?: string
  onFilter?: (key: string) => void
  stripe?: boolean
  hover?: boolean
  emptyMessage?: string
  className?: string
}

const ALIGN_CLASS: Record<string, string> = {
  left: "",
  center: "data-table-align-center",
  right: "data-table-align-right",
}

/**
 * DataTable — ARK Intelligence sortable table with optional filters
 */
export function DataTable<T extends { [key: string]: any }>({
  data,
  columns,
  title,
  filters,
  activeFilter,
  onFilter,
  emptyMessage = "No data available",
  className,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc")

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc")
    } else {
      setSortKey(key)
      setSortDir("asc")
    }
  }

  const sortedData = [...data].sort((a, b) => {
    if (!sortKey) return 0
    const aVal = a[sortKey]
    const bVal = b[sortKey]
    if (aVal < bVal) return sortDir === "asc" ? -1 : 1
    if (aVal > bVal) return sortDir === "asc" ? 1 : -1
    return 0
  })

  if (data.length === 0) {
    return (
      <div className="data-table-wrapper">
        {title && (
          <div className="data-table-toolbar">
            <span className="data-table-title">{title}</span>
          </div>
        )}
        <div className="empty-state">
          <div className="empty-state-title">{emptyMessage}</div>
        </div>
      </div>
    )
  }

  return (
    <div className={`data-table-wrapper${className ? ` ${className}` : ""}`}>
      {(title || filters) && (
        <div className="data-table-toolbar">
          {title && <span className="data-table-title">{title}</span>}
          {filters && (
            <div className="data-table-filters">
              {filters.map(f => (
                <button
                  key={f.key}
                  className={`filter-chip${activeFilter === f.key ? " active" : ""}`}
                  onClick={() => onFilter?.(f.key)}
                >
                  {f.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      <table className="data-table">
        <thead>
          <tr>
            {columns.map(col => (
              <th
                key={String(col.key)}
                className={`data-table-th-sortable ${ALIGN_CLASS[col.align || "left"]}`}
                onClick={() => handleSort(String(col.key))}
              >
                {col.label}
                {sortKey === String(col.key) && (sortDir === "asc" ? " ↑" : " ↓")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedData.map((row, i) => (
            <tr key={i}>
              {columns.map(col => (
                <td
                  key={String(col.key)}
                  className={col.align === "right" || col.align === "center" ? `data-table-mono ${ALIGN_CLASS[col.align || "left"]}` : ""}
                >
                  {col.render
                    ? col.render(row[col.key as keyof T], row)
                    : row[col.key as keyof T]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="data-table-footer">
        <span>{data.length} rows</span>
      </div>
    </div>
  )
}
