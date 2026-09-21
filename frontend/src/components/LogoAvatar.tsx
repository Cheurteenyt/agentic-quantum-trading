import { CSSProperties, useMemo, useState } from "react"
import hermesOrb from "../assets/branding/hermes-orb.png"

interface LogoAvatarProps {
  name?: string | null
  symbol?: string | null
  src?: string | null
  size?: number
  square?: boolean
  frame?: "default" | "bare"
  className?: string
  title?: string
  style?: CSSProperties
}

type KnownLogoKey =
  | "hermes"
  | "btc"
  | "eth"
  | "xau"
  | "usdt"
  | "usdc"
  | "dai"
  | "bnb"
  | "sol"
  | "trx"
  | "mt5"
  | "binance"
  | "blackrock"
  | "okx"
  | "uniswap"
  | "pancakeswap"
  | "polymarket"
  | "coinbase"
  | "kraken"
  | "kucoin"
  | "bitget"
  | "gate"
  | "mexc"
  | "bybit"

const officialBrandIconMap: Partial<Record<KnownLogoKey, string>> = {
  binance: "/brand-icons/binance.ico",
  blackrock: "/brand-icons/blackrock.png",
  okx: "/brand-icons/okx.png",
  uniswap: "/brand-icons/uniswap.png",
  pancakeswap: "/brand-icons/pancakeswap.png",
  polymarket: "/brand-icons/polymarket.png",
  coinbase: "/brand-icons/coinbase.ico",
  kraken: "/brand-icons/kraken.png",
  kucoin: "/brand-icons/kucoin.png",
  bitget: "/brand-icons/bitget.ico",
  gate: "/brand-icons/gate.ico",
  bybit: "/brand-icons/bybit.ico",
}

const normalize = (value?: string | null) =>
  String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "")

const initialsFromName = (name?: string | null, symbol?: string | null) => {
  if (symbol) return symbol.slice(0, 3).toUpperCase()
  const parts = String(name || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  if (parts.length === 0) return "?"
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase()
}

const resolveLogoKey = (name?: string | null, symbol?: string | null): KnownLogoKey | null => {
  const values = [normalize(symbol), normalize(name)].filter(Boolean)
  if (values.some((value) => value.includes("hermes"))) return "hermes"
  if (values.some((value) => value === "btc" || value.includes("bitcoin") || value.includes("wrappedbitcoin"))) return "btc"
  if (values.some((value) => value === "eth" || value.includes("ethereum") || value.includes("weth"))) return "eth"
  if (values.some((value) => value === "xau" || value.includes("gold") || value.includes("xauusd"))) return "xau"
  if (values.some((value) => value === "usdt" || value.includes("tether"))) return "usdt"
  if (values.some((value) => value === "usdc" || value.includes("usdcoin"))) return "usdc"
  if (values.some((value) => value === "dai" || value.includes("dai"))) return "dai"
  if (values.some((value) => value === "bnb" || value === "wbnb" || value.includes("wrappedbnb") || value.includes("binancecoin"))) return "bnb"
  if (values.some((value) => value === "sol" || value.includes("solana"))) return "sol"
  if (values.some((value) => value === "trx" || value.includes("tron"))) return "trx"
  if (values.some((value) => value.includes("mt5") || value.includes("puprime"))) return "mt5"
  if (values.some((value) => value.includes("binance"))) return "binance"
  if (values.some((value) => value.includes("blackrock"))) return "blackrock"
  if (values.some((value) => value === "okx" || value.includes("okx"))) return "okx"
  if (values.some((value) => value.includes("uniswap"))) return "uniswap"
  if (values.some((value) => value.includes("pancakeswap"))) return "pancakeswap"
  if (values.some((value) => value.includes("polymarket"))) return "polymarket"
  if (values.some((value) => value.includes("coinbase"))) return "coinbase"
  if (values.some((value) => value.includes("kraken"))) return "kraken"
  if (values.some((value) => value.includes("kucoin"))) return "kucoin"
  if (values.some((value) => value.includes("bitget"))) return "bitget"
  if (values.some((value) => value === "gate" || value.includes("gateio") || value.includes("gate"))) return "gate"
  if (values.some((value) => value.includes("mexc"))) return "mexc"
  if (values.some((value) => value.includes("bybit"))) return "bybit"
  return null
}

function KnownLogo({ logoKey, size }: { logoKey: KnownLogoKey; size: number }) {
  const common = { width: size, height: size, viewBox: "0 0 32 32", fill: "none" as const, xmlns: "http://www.w3.org/2000/svg" }
  const officialIcon = officialBrandIconMap[logoKey]

  if (officialIcon) {
    return <img src={officialIcon} alt={logoKey} className="logo-avatar-img" />
  }

  switch (logoKey) {
    case "hermes":
      return <img src={hermesOrb} alt="Hermes" className="logo-avatar-img" />
    case "btc":
      return (
        <svg {...common}>
          <defs>
            <linearGradient id="btcg" x1="7" y1="5" x2="25" y2="27" gradientUnits="userSpaceOnUse">
              <stop stopColor="#FFB347" />
              <stop offset="1" stopColor="#F7931A" />
            </linearGradient>
          </defs>
          <circle cx="16" cy="16" r="16" fill="url(#btcg)" />
          <circle cx="16" cy="16" r="15.25" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" />
          <g transform="rotate(-13 16 16)">
            <text
              x="16"
              y="20.8"
              textAnchor="middle"
              fontSize="15.5"
              fontWeight="700"
              fill="white"
              fontFamily="Arial, Helvetica, sans-serif"
            >
              ₿
            </text>
          </g>
        </svg>
      )
    case "eth":
      return (
        <svg {...common}>
          <defs>
            <linearGradient id="ethTop" x1="10" y1="4" x2="23" y2="16" gradientUnits="userSpaceOnUse">
              <stop stopColor="#E8EBFF" />
              <stop offset="1" stopColor="#8A92B2" />
            </linearGradient>
            <linearGradient id="ethBottom" x1="9" y1="17" x2="23" y2="28" gradientUnits="userSpaceOnUse">
              <stop stopColor="#8A92B2" />
              <stop offset="1" stopColor="#58607A" />
            </linearGradient>
          </defs>
          <circle cx="16" cy="16" r="16" fill="#111522" />
          <circle cx="16" cy="16" r="15.25" stroke="rgba(255,255,255,0.08)" strokeWidth="1.5" />
          <path d="M16 4.2L9.4 15.1L16 12.3L22.6 15.1L16 4.2Z" fill="url(#ethTop)" />
          <path d="M16 13.9L9.4 17.1L16 20.9L22.6 17.1L16 13.9Z" fill="#62688F" />
          <path d="M16 27.8L9.4 18.3L16 22.1L22.6 18.3L16 27.8Z" fill="url(#ethBottom)" />
        </svg>
      )
    case "xau":
      return (
        <svg {...common}>
          <defs>
            <radialGradient id="xauCoin" cx="0" cy="0" r="1" gradientTransform="translate(11 9) rotate(42) scale(18 19)" gradientUnits="userSpaceOnUse">
              <stop stopColor="#FFF2B2" />
              <stop offset="0.45" stopColor="#F7D56C" />
              <stop offset="1" stopColor="#B87408" />
            </radialGradient>
            <linearGradient id="xauBar" x1="10" y1="11.5" x2="22.8" y2="19.6" gradientUnits="userSpaceOnUse">
              <stop stopColor="#FFF3BF" />
              <stop offset="0.52" stopColor="#F0C249" />
              <stop offset="1" stopColor="#A66500" />
            </linearGradient>
          </defs>
          <circle cx="16" cy="16" r="16" fill="#130B02" />
          <circle cx="16" cy="16" r="12.4" fill="url(#xauCoin)" />
          <circle cx="16" cy="16" r="12.4" stroke="#FFD76C" strokeOpacity="0.65" strokeWidth="1.1" />
          <path d="M11 19L13.6 12.9H23L20.4 19H11Z" fill="url(#xauBar)" stroke="#8B5700" strokeWidth="0.8" strokeLinejoin="round" />
          <path d="M13.4 12.9H20.7L18.8 16.2H11.9L13.4 12.9Z" fill="#FFE7A0" fillOpacity="0.72" />
          <path d="M22.7 8.2L23.4 9.7L24.9 10.4L23.4 11.1L22.7 12.6L22 11.1L20.5 10.4L22 9.7L22.7 8.2Z" fill="#FFF8D6" />
        </svg>
      )
    case "usdt":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#26A17B" />
          <path d="M10 10H22V12.6H17.5V14.1C20.5 14.3 22.7 15 22.7 15.9C22.7 17 19.7 17.9 16 17.9C12.3 17.9 9.3 17 9.3 15.9C9.3 15 11.5 14.3 14.5 14.1V12.6H10V10Z" fill="white" />
          <path d="M15 12.6H17V22H15V12.6Z" fill="white" />
        </svg>
      )
    case "usdc":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#2775CA" />
          <circle cx="16" cy="16" r="9.4" fill="none" stroke="white" strokeWidth="2" />
          <path d="M17.9 11.4C17.2 10.9 16.4 10.6 15.4 10.6C13.6 10.6 12.4 11.5 12.4 12.9C12.4 14.2 13.3 14.9 15.2 15.4C16.8 15.8 17.3 16.1 17.3 17C17.3 18 16.4 18.6 15.1 18.6C14 18.6 13 18.3 12 17.6" stroke="white" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M15.7 9V10.6M15.7 18.6V20.2" stroke="white" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M8.6 12.2A8.8 8.8 0 0 0 8.2 16C8.4 20.2 11.8 23.4 16 23.4" stroke="white" strokeWidth="1.3" strokeLinecap="round" />
          <path d="M23.4 19.8A8.8 8.8 0 0 0 23.8 16C23.6 11.8 20.2 8.6 16 8.6" stroke="white" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      )
    case "dai":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#F5AC37" />
          <path d="M11 10H16.7C20.2 10 22.8 12.5 22.8 16C22.8 19.5 20.2 22 16.7 22H11V10Z" fill="#FFF6D9" />
          <path d="M13 13.1H17M13 16H18.2M13 18.9H17" stroke="#A56612" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      )
    case "bnb":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#111111" />
          <path d="M16 7L12.1 10.9L16 14.8L19.9 10.9L16 7Z" fill="#F3BA2F" />
          <path d="M9.6 13.4L7 16L9.6 18.6L12.2 16L9.6 13.4Z" fill="#F3BA2F" />
          <path d="M22.4 13.4L19.8 16L22.4 18.6L25 16L22.4 13.4Z" fill="#F3BA2F" />
          <path d="M16 17.2L12.8 20.4L16 23.6L19.2 20.4L16 17.2Z" fill="#F3BA2F" />
          <path d="M16 13.2L13.2 16L16 18.8L18.8 16L16 13.2Z" fill="#F3BA2F" />
        </svg>
      )
    case "sol":
      return (
        <svg {...common}>
          <defs>
            <linearGradient id="solg" x1="6" y1="8" x2="25" y2="24" gradientUnits="userSpaceOnUse">
              <stop stopColor="#00FFA3" />
              <stop offset="0.55" stopColor="#7B5CFF" />
              <stop offset="1" stopColor="#00D1FF" />
            </linearGradient>
          </defs>
          <rect width="32" height="32" rx="10" fill="#0B0E17" />
          <path d="M10 10.2H24L21.2 13.4H7.2L10 10.2Z" fill="url(#solg)" />
          <path d="M7.2 15.2H21.2L24 18.4H10L7.2 15.2Z" fill="url(#solg)" />
          <path d="M10 20.2H24L21.2 23.4H7.2L10 20.2Z" fill="url(#solg)" />
        </svg>
      )
    case "trx":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#FF1E1E" />
          <path d="M8.8 9.5L22.5 12.2L18.2 22.6L8.8 9.5Z" fill="none" stroke="white" strokeWidth="1.7" strokeLinejoin="round" />
          <path d="M13.4 13.1L18.2 22.6" stroke="white" strokeWidth="1.4" strokeLinejoin="round" />
          <path d="M13.4 13.1L22.5 12.2" stroke="white" strokeWidth="1.4" strokeLinejoin="round" />
        </svg>
      )
    case "mt5":
      return (
        <svg {...common}>
          <rect x="0" y="0" width="32" height="32" rx="10" fill="#102957" />
          <path d="M9 22V10H11.5L16 16.2L20.5 10H23V22H20.2V15.4L16.2 20.8H15.8L11.8 15.4V22H9Z" fill="#52A6FF" />
          <path d="M24.4 10H29V12.4H26.9V22H24.4V10Z" fill="#94C8FF" />
        </svg>
      )
    case "binance":
      return (
        <svg {...common}>
          <g fill="#F3BA2F">
            <path d="M16 3.8L9.7 10.1L13.1 13.5L16 10.6L18.9 13.5L22.3 10.1L16 3.8Z" />
            <path d="M7.4 12.4L4.5 15.3L7.9 18.7L10.8 15.8L7.4 12.4Z" />
            <path d="M24.6 12.4L21.2 15.8L24.1 18.7L27.5 15.3L24.6 12.4Z" />
            <path d="M16 12.1L12.6 15.5L16 18.9L19.4 15.5L16 12.1Z" />
            <path d="M13.1 17.5L9.7 20.9L16 27.2L22.3 20.9L18.9 17.5L16 20.4L13.1 17.5Z" />
          </g>
        </svg>
      )
    case "blackrock":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#060606" />
          <text x="16" y="13.5" textAnchor="middle" fontSize="5.2" fontWeight="700" fill="white" fontFamily="Arial, Helvetica, sans-serif">Black</text>
          <text x="16" y="19.7" textAnchor="middle" fontSize="5.8" fontWeight="700" fill="white" fontFamily="Arial, Helvetica, sans-serif">Rock</text>
        </svg>
      )
    case "okx":
      return (
        <svg {...common}>
          <rect width="32" height="32" rx="10" fill="#0A0A0A" />
          <rect x="6" y="6" width="6" height="6" rx="1.5" fill="white" />
          <rect x="13" y="6" width="6" height="6" rx="1.5" fill="white" />
          <rect x="20" y="6" width="6" height="6" rx="1.5" fill="white" />
          <rect x="6" y="13" width="6" height="6" rx="1.5" fill="white" />
          <rect x="20" y="13" width="6" height="6" rx="1.5" fill="white" />
          <rect x="6" y="20" width="6" height="6" rx="1.5" fill="white" />
          <rect x="13" y="20" width="6" height="6" rx="1.5" fill="white" />
          <rect x="20" y="20" width="6" height="6" rx="1.5" fill="white" />
        </svg>
      )
    case "uniswap":
      return (
        <svg {...common}>
          <defs>
            <linearGradient id="unig" x1="5" y1="4" x2="26" y2="28" gradientUnits="userSpaceOnUse">
              <stop stopColor="#FF92CB" />
              <stop offset="1" stopColor="#FF2D96" />
            </linearGradient>
          </defs>
          <circle cx="16" cy="16" r="16" fill="url(#unig)" />
          <path d="M11.4 22.2C13.7 20.4 17.1 18.5 19.9 16.7C21.4 15.7 22.3 14.4 22.3 12.9C22.3 11.8 21.6 10.9 20.6 10.9C19.8 10.9 19.2 11.3 18.8 11.9C18.2 10.6 16.8 9.7 15.1 9.7C12.3 9.7 10.2 12 10.2 14.9C10.2 17.5 11.8 19.4 14.2 19.9L12.7 22.7L11.4 22.2Z" fill="white" />
          <circle cx="22.7" cy="8.7" r="1.4" fill="white" />
        </svg>
      )
    case "pancakeswap":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#1B1207" />
          <path d="M10 13.3C10 10.9 12 9 14.5 9H17.5C20 9 22 10.9 22 13.3V18.1C22 20.5 20 22.4 17.5 22.4H14.5C12 22.4 10 20.5 10 18.1V13.3Z" fill="#D9A441" />
          <path d="M12.7 12.1C12.7 10.9 13.7 10 14.9 10C16.1 10 17.1 10.9 17.1 12.1" stroke="#5B3B15" strokeWidth="1.4" strokeLinecap="round" />
          <circle cx="13.6" cy="15.7" r="1" fill="#5B3B15" />
          <circle cx="18.4" cy="15.7" r="1" fill="#5B3B15" />
          <path d="M14 18.6C14.8 19.2 17.2 19.2 18 18.6" stroke="#5B3B15" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
      )
    case "polymarket":
      return (
        <svg {...common}>
          <rect width="32" height="32" rx="10" fill="#2E5CFF" />
          <path
            d="M8.4 11.8L22.1 8.1V23.9L8.4 20.2V11.8Z"
            stroke="white"
            strokeWidth="2.6"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <path
            d="M8.4 15.9L22.1 12.2"
            stroke="white"
            strokeWidth="2.6"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </svg>
      )
    case "coinbase":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#1652F0" />
          <circle cx="16" cy="16" r="7.5" fill="white" />
          <circle cx="16" cy="16" r="3.8" fill="#1652F0" />
        </svg>
      )
    case "kraken":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#5A53FF" />
          <path d="M10 20.5V15.4C10 12.5 12.4 10.2 15.3 10.2H16.7C19.6 10.2 22 12.5 22 15.4V20.5" stroke="white" strokeWidth="2.4" strokeLinecap="round" />
          <path d="M11.3 20.7V23.1M14.7 20.7V23.1M18 20.7V23.1M21.3 20.7V23.1" stroke="white" strokeWidth="2" strokeLinecap="round" />
        </svg>
      )
    case "kucoin":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#00D9A5" />
          <path d="M11 9V23" stroke="#0A1624" strokeWidth="2.4" strokeLinecap="round" />
          <path d="M20.8 9.6A2 2 0 1 1 20.8 13.6A2 2 0 0 1 20.8 9.6Z" fill="#0A1624" />
          <path d="M20.8 18.4A2 2 0 1 1 20.8 22.4A2 2 0 0 1 20.8 18.4Z" fill="#0A1624" />
          <path d="M12.8 16L18.9 11.3M12.8 16L18.9 20.7" stroke="#0A1624" strokeWidth="2.4" strokeLinecap="round" />
        </svg>
      )
    case "bitget":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#0D1624" />
          <path d="M9.5 18.8L15.2 13.1H11.5V10.5H21.8V20.8H19.2V17.1L13.5 22.8L9.5 18.8Z" fill="#19C2D8" />
        </svg>
      )
    case "gate":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#D83028" />
          <path d="M20.5 12.2A6.7 6.7 0 1 0 21 18.8H17.1V16.3H24V23.2H21.5V21.9A8.8 8.8 0 1 1 20.5 12.2Z" fill="white" />
        </svg>
      )
    case "mexc":
      return (
        <svg {...common}>
          <defs>
            <linearGradient id="mexcg" x1="6" y1="5" x2="26" y2="27" gradientUnits="userSpaceOnUse">
              <stop stopColor="#00D0C7" />
              <stop offset="1" stopColor="#3C8CFF" />
            </linearGradient>
          </defs>
          <circle cx="16" cy="16" r="16" fill="#07111E" />
          <path d="M8.5 21.5V10.5L13.5 15.7L16 13.1L18.5 15.7L23.5 10.5V21.5H20.8V16.8L18.1 19.6H13.9L11.2 16.8V21.5H8.5Z" fill="url(#mexcg)" />
        </svg>
      )
    case "bybit":
      return (
        <svg {...common}>
          <circle cx="16" cy="16" r="16" fill="#111111" />
          <path d="M11 9H13.7L16 13.6L18.3 9H21L17.4 15.7L21 23H18.3L16 18.4L13.7 23H11L14.6 15.7L11 9Z" fill="white" />
          <rect x="22.2" y="9.6" width="1.8" height="12.8" rx="0.9" fill="#F7A600" />
        </svg>
      )
    default:
      return null
  }
}

export default function LogoAvatar({
  name,
  symbol,
  src,
  size = 24,
  square = false,
  className = "",
  title,
  style,
}: LogoAvatarProps) {
  const [imgFailed, setImgFailed] = useState(false)
  const logoKey = useMemo(() => resolveLogoKey(name, symbol), [name, symbol])
  const initials = useMemo(() => initialsFromName(name, symbol), [name, symbol])

  const rootStyle: CSSProperties = {
    width: size,
    height: size,
    borderRadius: square ? 10 : 999,
    ...style,
  }

  const rootClassName = `logo-avatar${square ? " is-square" : ""}${className ? ` ${className}` : ""}`

  if (src && !imgFailed) {
    return (
      <span className={rootClassName} style={rootStyle} title={title || name || symbol || "logo"}>
        <img src={src} alt={name || symbol || "logo"} className="logo-avatar-img" onError={() => setImgFailed(true)} />
      </span>
    )
  }

  if (logoKey) {
    return (
      <span className={rootClassName} style={rootStyle} title={title || name || symbol || logoKey}>
        <KnownLogo logoKey={logoKey} size={size} />
      </span>
    )
  }

  return (
    <span className={rootClassName} style={rootStyle} title={title || name || symbol || initials}>
      <span className="logo-avatar-fallback" style={{ fontSize: Math.max(10, Math.round(size * 0.34)) }}>
        {initials}
      </span>
    </span>
  )
}
