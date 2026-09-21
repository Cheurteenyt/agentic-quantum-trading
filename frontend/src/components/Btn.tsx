interface BtnProps {
  onClick?: () => void
  children: React.ReactNode
  variant?: "default" | "primary" | "danger" | "success" | "purple" | "ghost"
  disabled?: boolean
  loading?: boolean
  size?: "sm" | "md" | "lg"
  className?: string
}

const VARIANT_CLASS: Record<string, string> = {
  default: "btn-default",
  primary: "btn-primary",
  danger: "btn-danger",
  success: "btn-success",
  purple: "btn-primary",
  ghost: "btn-ghost",
}

const SIZE_CLASS: Record<string, string> = {
  sm: "btn-sm",
  md: "",
  lg: "btn-lg",
}

/**
 * Btn — ARK Intelligence button with variants and sizes
 */
export function Btn({
  onClick,
  children,
  variant = "default",
  disabled = false,
  loading = false,
  size = "md",
  className,
}: BtnProps) {
  const classes = [
    "btn",
    VARIANT_CLASS[variant] || "btn-default",
    SIZE_CLASS[size],
    className || "",
  ].filter(Boolean).join(" ")

  return (
    <button
      className={classes}
      onClick={onClick}
      disabled={disabled || loading}
    >
      {loading ? (
        <>
          <span className="btn-spinner" />
          <span>...</span>
        </>
      ) : children}
    </button>
  )
}
