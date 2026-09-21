import React from 'react';
import {Audio} from '@remotion/media';
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

type TrailerProps = {
  launchLine: string;
};

const clamp = {
  extrapolateLeft: 'clamp' as const,
  extrapolateRight: 'clamp' as const,
};

const C = {
  black: '#02040a',
  deep: '#040915',
  navy: '#06182f',
  blue: '#116bff',
  cyan: '#63f3ff',
  teal: '#00d6c8',
  amber: '#f8d57a',
  red: '#ff315f',
  white: '#f5fbff',
  soft: 'rgba(223, 241, 255, 0.74)',
  dim: 'rgba(174, 205, 229, 0.46)',
  line: 'rgba(99, 243, 255, 0.25)',
};

const displayFont = 'Bodoni 72, Didot, Georgia, Times New Roman, serif';
const techFont = 'Bahnschrift, Rajdhani, Tahoma, Verdana, sans-serif';

const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);
const easeSnap = Easing.bezier(0.25, 1.55, 0.34, 1);

const progress = (frame: number, start: number, duration: number, easing = easeOut) =>
  interpolate(frame, [start, start + duration], [0, 1], {
    ...clamp,
    easing,
  });

const fadeOut = (frame: number, start: number, duration = 24) =>
  interpolate(frame, [start, start + duration], [1, 0], {
    ...clamp,
    easing: Easing.in(Easing.cubic),
  });

const sceneOpacity = (frame: number, leave: number, enter = 0) =>
  progress(frame, enter, 20, easeOut) * fadeOut(frame, leave, 24);

const pulse = (frame: number, offset = 0, speed = 6.5) =>
  interpolate(Math.sin((frame + offset) / speed), [-1, 1], [0, 1], clamp);

const hashNoise = (index: number, salt = 1) => {
  const x = Math.sin(index * 999 + salt * 71) * 10000;
  return x - Math.floor(x);
};

const CinematicBase = ({intensity = 1}: {intensity?: number}) => {
  const frame = useCurrentFrame();
  const glow = pulse(frame, 0, 7);
  const drift = frame * 0.55;

  return (
    <AbsoluteFill style={{overflow: 'hidden', backgroundColor: C.black}}>
      <AbsoluteFill
        style={{
          background:
            `radial-gradient(circle at ${64 + Math.sin(frame / 88) * 7}% ${20 + Math.cos(frame / 112) * 5}%, rgba(17, 107, 255, ${0.26 * intensity}), transparent 34%), ` +
            `radial-gradient(circle at ${22 + Math.sin(frame / 117) * 6}% 82%, rgba(0, 214, 200, ${0.14 * intensity + glow * 0.08}), transparent 35%), ` +
            `linear-gradient(135deg, ${C.black}, ${C.deep} 44%, #000105 100%)`,
        }}
      />
      <div
        style={{
          position: 'absolute',
          inset: -220,
          backgroundImage:
            'linear-gradient(rgba(99,243,255,0.075) 1px, transparent 1px), linear-gradient(90deg, rgba(99,243,255,0.055) 1px, transparent 1px)',
          backgroundSize: '86px 86px',
          transform: `translate3d(${drift % 86}px, ${(drift * 0.66) % 86}px, 0) rotate(-10deg) scale(1.1)`,
          opacity: 0.36,
        }}
      />
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'linear-gradient(90deg, rgba(0,0,0,0.82), rgba(0,0,0,0.08) 45%, rgba(0,0,0,0.68)), linear-gradient(180deg, rgba(0,0,0,0.24), transparent 40%, rgba(0,0,0,0.55))',
        }}
      />
      {Array.from({length: 70}).map((_, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            left: `${hashNoise(i, 3) * 100}%`,
            top: `${hashNoise(i, 9) * 100}%`,
            width: 1 + hashNoise(i, 12) * 2,
            height: 1 + hashNoise(i, 18) * 2,
            borderRadius: '50%',
            background: i % 6 === 0 ? C.cyan : 'rgba(255,255,255,0.55)',
            opacity: 0.06 + pulse(frame, i * 5, 12 + (i % 4)) * 0.24,
            boxShadow: i % 6 === 0 ? '0 0 16px rgba(99,243,255,0.8)' : undefined,
          }}
        />
      ))}
    </AbsoluteFill>
  );
};

const CinemaBars = () => (
  <AbsoluteFill style={{pointerEvents: 'none'}}>
    <div style={{position: 'absolute', top: 0, left: 0, right: 0, height: 86, background: 'rgba(0,0,0,0.76)'}} />
    <div style={{position: 'absolute', bottom: 0, left: 0, right: 0, height: 86, background: 'rgba(0,0,0,0.76)'}} />
    <AbsoluteFill style={{boxShadow: 'inset 0 0 320px rgba(0,0,0,0.75)'}} />
  </AbsoluteFill>
);

const TrailerHud = ({label = 'CORE EQUITY'}: {label?: string}) => {
  const frame = useCurrentFrame();
  const scan = (frame * 7) % 1080;
  return (
    <AbsoluteFill style={{pointerEvents: 'none', opacity: 0.7}}>
      <div
        style={{
          position: 'absolute',
          left: 56,
          top: 42,
          width: 240,
          height: 1,
          background: 'linear-gradient(90deg, transparent, rgba(99,243,255,0.8), transparent)',
          boxShadow: '0 0 18px rgba(99,243,255,0.75)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          right: 56,
          bottom: 42,
          width: 240,
          height: 1,
          background: 'linear-gradient(90deg, transparent, rgba(99,243,255,0.8), transparent)',
          boxShadow: '0 0 18px rgba(99,243,255,0.75)',
        }}
      />
      <div style={{position: 'absolute', left: 56, bottom: 40, fontFamily: techFont, fontSize: 12, letterSpacing: '0.28em', color: 'rgba(99,243,255,0.55)', textTransform: 'uppercase'}}>
        {label} / private market intelligence
      </div>
      <div style={{position: 'absolute', right: 56, top: 40, fontFamily: techFont, fontSize: 12, letterSpacing: '0.28em', color: 'rgba(99,243,255,0.55)', textTransform: 'uppercase'}}>
        proof first / risk locked
      </div>
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: scan,
          height: 2,
          background: 'linear-gradient(90deg, transparent, rgba(99,243,255,0.32), transparent)',
          filter: 'blur(1px)',
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.08,
          backgroundImage: 'linear-gradient(rgba(255,255,255,0.08) 1px, transparent 1px)',
          backgroundSize: '100% 4px',
        }}
      />
    </AbsoluteFill>
  );
};

const ImpactWord = ({at, word, sub}: {at: number; word: string; sub: string}) => {
  const frame = useCurrentFrame();
  const local = frame - at;
  const show = progress(local, 0, 7, easeSnap) * fadeOut(local, 28, 12);
  const slice = progress(local, 2, 10, easeInOut);
  if (local < -2 || local > 44) {
    return null;
  }

  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        opacity: show,
        background: 'radial-gradient(circle at 50% 50%, rgba(99,243,255,0.22), rgba(0,0,0,0.88) 58%, rgba(0,0,0,0.94))',
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: 318,
          textAlign: 'center',
          fontFamily: displayFont,
          fontSize: 184,
          lineHeight: 0.82,
          letterSpacing: '-0.09em',
          color: C.white,
          fontWeight: 900,
          textTransform: 'uppercase',
          transform: `translateX(${interpolate(slice, [0, 1], [-90, 0])}px) scale(${interpolate(show, [0, 1], [1.18, 1])})`,
          textShadow: '0 0 70px rgba(99,243,255,0.65), 0 30px 140px rgba(17,107,255,0.6)',
        }}
      >
        {word}
      </div>
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: 520,
          textAlign: 'center',
          fontFamily: techFont,
          fontSize: 22,
          letterSpacing: '0.42em',
          color: C.cyan,
          textTransform: 'uppercase',
          transform: `translateX(${interpolate(slice, [0, 1], [120, 0])}px)`,
        }}
      >
        {sub}
      </div>
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            left: `${8 + i * 24}%`,
            top: `${25 + i * 11}%`,
            width: `${220 + i * 140}px`,
            height: 3,
            background: i % 2 ? C.blue : C.cyan,
            opacity: show * (0.35 + i * 0.1),
            transform: `translateX(${interpolate(slice, [0, 1], [-500 + i * 80, 500 - i * 70])}px)`,
            boxShadow: `0 0 30px ${i % 2 ? C.blue : C.cyan}`,
          }}
        />
      ))}
    </AbsoluteFill>
  );
};

const Sweep = ({delay = 0, strong = 1}: {delay?: number; strong?: number}) => {
  const frame = useCurrentFrame();
  const on = progress((frame - delay) % 150, 0, 26, easeInOut) * fadeOut((frame - delay) % 150, 30, 28);
  return (
    <div
      style={{
        position: 'absolute',
        inset: -300,
        opacity: on * 0.65 * strong,
        background: 'linear-gradient(90deg, transparent, rgba(99,243,255,0.52), rgba(17,107,255,0.58), transparent)',
        transform: `translateX(${interpolate(on, [0, 1], [-1450, 900])}px) rotate(-17deg)`,
        filter: 'blur(16px)',
      }}
    />
  );
};

const CutFlash = ({start}: {start: number}) => {
  const frame = useCurrentFrame();
  const on = progress(frame, start, 5, easeOut) * fadeOut(frame, start + 5, 10);
  return (
    <AbsoluteFill
      style={{
        opacity: on,
        background: 'linear-gradient(90deg, rgba(255,255,255,0), rgba(99,243,255,0.85), rgba(255,255,255,0))',
        transform: `translateX(${interpolate(on, [0, 1], [-900, 900])}px) skewX(-18deg)`,
        filter: 'blur(2px)',
      }}
    />
  );
};

const AnimatedLogoGlyph = ({frame, compact = false}: {frame: number; compact?: boolean}) => {
  const arms = [
    {d: 'M50 50 C47 36 50 26 58 18', x: 58, y: 18},
    {d: 'M50 50 C39 36 31 30 21 32', x: 21, y: 32},
    {d: 'M50 50 C36 48 25 53 16 61', x: 16, y: 61},
    {d: 'M50 50 C39 61 37 72 43 84', x: 43, y: 84},
    {d: 'M50 50 C54 64 60 74 70 81', x: 70, y: 81},
    {d: 'M50 50 C64 52 76 56 85 63', x: 85, y: 63},
    {d: 'M50 50 C65 43 72 35 80 25', x: 80, y: 25},
    {d: 'M50 50 C58 38 66 32 73 28', x: 73, y: 28},
  ];
  const drawBase = compact ? 12 : 22;
  const whole = progress(frame, 0, 52, easeSnap);
  const breath = pulse(frame, 0, 5.2);
  return (
    <svg
      viewBox="0 0 100 100"
      style={{
        position: 'absolute',
        left: '18%',
        top: '17%',
        width: '64%',
        height: '64%',
        overflow: 'visible',
        opacity: 0.84 + breath * 0.16,
        mixBlendMode: 'screen',
        filter: `drop-shadow(0 0 ${8 + breath * 12}px rgba(255,255,255,0.95)) drop-shadow(0 0 ${22 + breath * 24}px rgba(99,243,255,0.72))`,
      }}
    >
      <defs>
        <radialGradient id="coreGlyphGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
          <stop offset="45%" stopColor="#c9fbff" stopOpacity="0.88" />
          <stop offset="100%" stopColor="#63f3ff" stopOpacity="0.08" />
        </radialGradient>
      </defs>
      {arms.map((arm, i) => {
        const show = progress(frame, drawBase + i * 3, 24, easeOut);
        const dash = 58;
        const shimmer = pulse(frame, i * 7, 6);
        return (
          <g key={arm.d}>
            <path
              d={arm.d}
              fill="none"
              stroke="rgba(99,243,255,0.32)"
              strokeWidth={7.6}
              strokeLinecap="round"
              strokeDasharray={dash}
              strokeDashoffset={(1 - show) * dash}
              opacity={show * 0.55}
            />
            <path
              d={arm.d}
              fill="none"
              stroke="#ffffff"
              strokeWidth={4.3 + shimmer * 0.55}
              strokeLinecap="round"
              strokeDasharray={dash}
              strokeDashoffset={(1 - show) * dash}
              opacity={show}
            />
            <circle
              cx={arm.x}
              cy={arm.y}
              r={(2.8 + shimmer * 1.1) * show}
              fill="#ffffff"
              opacity={show}
            />
            <circle
              cx={arm.x}
              cy={arm.y}
              r={(6.8 + shimmer * 4.2) * show}
              fill="rgba(99,243,255,0.18)"
              opacity={show}
            />
          </g>
        );
      })}
      <circle cx="50" cy="50" r={8 + breath * 2.6} fill="url(#coreGlyphGlow)" opacity={whole} />
      <circle cx="50" cy="50" r={18 + breath * 11} fill="rgba(99,243,255,0.14)" opacity={whole} />
    </svg>
  );
};

const Orb = ({variant = 'hero'}: {variant?: 'hero' | 'center' | 'giant' | 'mark'}) => {
  const frame = useCurrentFrame();
  const active = progress(frame, 0, 44, easeSnap);
  const beat = pulse(frame, 0, 6);
  const size = variant === 'giant' ? 470 : variant === 'center' ? 330 : variant === 'mark' ? 118 : 315;
  const spin = frame * (variant === 'mark' ? 1.05 : 0.48);
  const flicker = pulse(frame, 8, 3.4) * pulse(frame, 21, 11);

  const pos =
    variant === 'center'
      ? {left: '50%', top: 115, transformBase: 'translateX(-50%)'}
      : variant === 'giant'
        ? {right: 82, top: 250, transformBase: ''}
        : variant === 'mark'
          ? {right: 92, top: 74, transformBase: ''}
          : {right: 240, top: 350, transformBase: ''};

  return (
    <div
      style={{
        position: 'absolute',
        width: size,
        height: size,
        left: pos.left,
        right: pos.right,
        top: pos.top,
        transform: `${pos.transformBase} scale(${0.72 + active * 0.28 + beat * 0.022})`,
        filter: `drop-shadow(0 0 ${44 + beat * 54}px rgba(99,243,255,${0.5 + beat * 0.26}))`,
      }}
    >
      {[0, 1, 2, 3].map((ring) => (
        <div
          key={ring}
          style={{
            position: 'absolute',
            inset: -34 - ring * 26,
            borderRadius: '50%',
            border: `${ring === 0 ? 2 : 1}px solid rgba(99,243,255,${0.26 - ring * 0.045})`,
            transform: `rotate(${spin * (ring % 2 ? -1 : 1) + ring * 38}deg) scale(${1 + ring * 0.036 + beat * 0.02})`,
            boxShadow: `0 0 ${35 + ring * 22}px rgba(17,107,255,${0.12 + beat * 0.1})`,
          }}
        />
      ))}
      {Array.from({length: 12}).map((_, i) => {
        const angle = (i / 12) * Math.PI * 2 + frame / (36 + (i % 3) * 6);
        const radius = size * (0.55 + (i % 3) * 0.06);
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: size / 2 + Math.cos(angle) * radius,
              top: size / 2 + Math.sin(angle) * radius,
              width: 5 + (i % 3) * 2,
              height: 5 + (i % 3) * 2,
              borderRadius: '50%',
              background: i % 4 === 0 ? C.white : C.cyan,
              opacity: 0.16 + beat * 0.4,
              boxShadow: '0 0 22px rgba(99,243,255,0.9)',
            }}
          />
        );
      })}
      <div
        style={{
          position: 'absolute',
          inset: -70,
          borderRadius: '50%',
          background: `radial-gradient(circle, rgba(99,243,255,${0.18 + beat * 0.16}), transparent 64%)`,
        }}
      />
      <div
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius: '50%',
          overflow: 'hidden',
        }}
      >
        <Img
          src={staticFile('core-equity-orb.png')}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            transform: `rotate(${Math.sin(frame / 54) * 2.4}deg) scale(${1 + beat * 0.014})`,
            filter: `saturate(${1.08 + beat * 0.22}) contrast(${1.08 + flicker * 0.14})`,
          }}
        />
        <AnimatedLogoGlyph frame={frame} compact={variant === 'mark'} />
        <div
          style={{
            position: 'absolute',
            inset: '17%',
            borderRadius: '50%',
            background: `radial-gradient(circle, rgba(255,255,255,${0.08 + beat * 0.1}), rgba(99,243,255,${0.05 + beat * 0.06}) 36%, transparent 67%)`,
            mixBlendMode: 'screen',
          }}
        />
      </div>
      <div
        style={{
          position: 'absolute',
          inset: -6,
          borderRadius: '50%',
          border: `1px solid rgba(255,255,255,${0.16 + beat * 0.18})`,
          boxShadow: `inset 0 0 ${42 + beat * 36}px rgba(255,255,255,0.08), 0 0 ${35 + beat * 50}px rgba(99,243,255,0.32)`,
        }}
      />
    </div>
  );
};

const Kicker = ({children, color = C.cyan}: React.PropsWithChildren<{color?: string}>) => (
  <div
    style={{
      fontFamily: techFont,
      fontSize: 22,
      letterSpacing: '0.42em',
      color,
      textTransform: 'uppercase',
      fontWeight: 900,
      textShadow: `0 0 28px ${color}`,
    }}
  >
    {children}
  </div>
);

const MassiveTitle = ({
  children,
  size = 126,
  align = 'left',
}: React.PropsWithChildren<{size?: number; align?: 'left' | 'center'}>) => (
  <div
    style={{
      fontFamily: displayFont,
      fontSize: size,
      lineHeight: 0.86,
      letterSpacing: '-0.072em',
      color: C.white,
      fontWeight: 900,
      textAlign: align,
      textShadow: '0 18px 95px rgba(17,107,255,0.55), 0 0 28px rgba(255,255,255,0.18)',
    }}
  >
    {children}
  </div>
);

const Body = ({children, width = 840}: React.PropsWithChildren<{width?: number}>) => (
  <div
    style={{
      marginTop: 28,
      width,
      fontFamily: techFont,
      fontSize: 30,
      lineHeight: 1.25,
      color: C.soft,
      letterSpacing: '-0.02em',
    }}
  >
    {children}
  </div>
);

const Reveal = ({frame, delay = 0, children}: React.PropsWithChildren<{frame: number; delay?: number}>) => {
  const show = progress(frame, delay, 28, easeOut);
  return (
    <div
      style={{
        opacity: show,
        transform: `translate3d(0, ${interpolate(show, [0, 1], [52, 0])}px, 0) scale(${interpolate(show, [0, 1], [0.985, 1])})`,
      }}
    >
      {children}
    </div>
  );
};

const WordReveal = ({text, frame, delay = 0, size = 98}: {text: string; frame: number; delay?: number; size?: number}) => {
  const words = text.split(' ');
  return (
    <div style={{fontFamily: displayFont, fontSize: size, lineHeight: 0.9, fontWeight: 900, letterSpacing: '-0.07em', color: C.white}}>
      {words.map((word, i) => {
        const show = progress(frame, delay + i * 6, 18, easeSnap);
        return (
          <span
            key={`${word}-${i}`}
            style={{
              display: 'inline-block',
              marginRight: '0.22em',
              opacity: show,
              transform: `translateY(${interpolate(show, [0, 1], [70, 0])}px) rotate(${interpolate(show, [0, 1], [3, 0])}deg)`,
              textShadow: `0 0 ${20 + show * 40}px rgba(99,243,255,0.22)`,
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
};

const MarketTape = ({frame, y = 880}: {frame: number; y?: number}) => {
  const rows = [
    'WALLET FLOW +284%   POOL ACTIVITY +71%   LIQUIDITY SHIFT   REPEAT BUYERS   RISK CHECK',
    'SOL/USDT   LINK/USDT   AAVE/USDT   BSC POOL   ETH FLOW   SMART WALLET   SOURCE CHECK',
  ];
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: y, overflow: 'hidden', opacity: 0.5}}>
      {rows.map((row, i) => (
        <div
          key={row}
          style={{
            whiteSpace: 'nowrap',
            transform: `translateX(${((i ? frame * 3.8 : -frame * 4.7) % 1280) - 520}px)`,
            fontFamily: techFont,
            color: i ? C.dim : C.cyan,
            fontSize: 18,
            letterSpacing: '0.24em',
            lineHeight: 2.2,
            textTransform: 'uppercase',
          }}
        >
          {row} &nbsp;&nbsp;&nbsp; {row} &nbsp;&nbsp;&nbsp; {row}
        </div>
      ))}
    </div>
  );
};

const FlowNetwork = ({compact = false}: {compact?: boolean}) => {
  const frame = useCurrentFrame();
  const nodes = [
    {x: 190, y: 210, label: 'wallet'},
    {x: 470, y: 145, label: 'pool'},
    {x: 760, y: 250, label: 'route'},
    {x: 1020, y: 170, label: 'source'},
    {x: 1280, y: 318, label: 'risk'},
    {x: 1460, y: 520, label: 'signal'},
    {x: 1050, y: 640, label: 'proof'},
    {x: 720, y: 555, label: 'swap'},
    {x: 390, y: 650, label: 'flow'},
    {x: 230, y: 470, label: 'cluster'},
  ];
  const edges = [
    [0, 1],
    [1, 2],
    [2, 3],
    [3, 4],
    [4, 5],
    [2, 7],
    [7, 6],
    [6, 4],
    [8, 7],
    [9, 8],
    [0, 9],
    [1, 7],
  ];
  const scale = compact ? 0.82 : 1;
  const alpha = progress(frame, 12, 42);
  return (
    <div
      style={{
        position: 'absolute',
        left: compact ? 420 : 110,
        top: compact ? 240 : 160,
        width: 1560,
        height: 700,
        opacity: alpha,
        transform: `scale(${scale}) perspective(900px) rotateX(8deg) rotateZ(${Math.sin(frame / 110) * 1.8}deg)`,
        transformOrigin: 'center',
      }}
    >
      <svg width="1560" height="700" style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
        {edges.map(([a, b], i) => {
          const n1 = nodes[a];
          const n2 = nodes[b];
          return (
            <line
              key={`${a}-${b}`}
              x1={n1.x}
              y1={n1.y}
              x2={n2.x}
              y2={n2.y}
              stroke={i % 3 === 0 ? C.cyan : C.blue}
              strokeWidth={i % 4 === 0 ? 3 : 1.5}
              strokeDasharray="10 24"
              strokeDashoffset={-frame * (3 + (i % 3))}
              opacity={0.32 + pulse(frame, i * 8, 9) * 0.38}
            />
          );
        })}
      </svg>
      {nodes.map((node, i) => {
        const beat = pulse(frame, i * 5, 7 + (i % 3));
        const show = progress(frame, 28 + i * 3, 18, easeSnap);
        return (
          <div
            key={node.label}
            style={{
              position: 'absolute',
              left: node.x - 12,
              top: node.y - 12,
              opacity: show,
              transform: `scale(${0.75 + show * 0.25 + beat * 0.14})`,
            }}
          >
            <div
              style={{
                width: 22 + (i % 3) * 8,
                height: 22 + (i % 3) * 8,
                borderRadius: '50%',
                background: i % 5 === 0 ? C.amber : i % 4 === 0 ? C.teal : C.cyan,
                boxShadow: `0 0 ${22 + beat * 42}px ${i % 5 === 0 ? C.amber : C.cyan}`,
              }}
            />
            <div
              style={{
                marginTop: 10,
                marginLeft: -22,
                fontFamily: techFont,
                fontSize: 14,
                color: C.dim,
                letterSpacing: '0.16em',
                textTransform: 'uppercase',
              }}
            >
              {node.label}
            </div>
          </div>
        );
      })}
    </div>
  );
};

const Radar = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: 'absolute', right: 145, top: 185, width: 620, height: 620}}>
      {[0, 1, 2, 3, 4].map((i) => {
        const grow = ((frame * 1.8 + i * 38) % 180) / 180;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: `${50 - grow * 43}%`,
              top: `${50 - grow * 43}%`,
              width: `${grow * 86}%`,
              height: `${grow * 86}%`,
              borderRadius: '50%',
              border: '1px solid rgba(99,243,255,0.34)',
              opacity: 1 - grow,
              boxShadow: '0 0 44px rgba(99,243,255,0.12)',
            }}
          />
        );
      })}
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: '50%',
          width: 4,
          height: 310,
          transformOrigin: 'top center',
          transform: `rotate(${frame * 2.1}deg)`,
          background: 'linear-gradient(180deg, rgba(99,243,255,0.9), transparent)',
          filter: 'blur(0.5px)',
        }}
      />
      <Orb variant="center" />
    </div>
  );
};

const StatPill = ({label, value, frame, delay}: {label: string; value: string; frame: number; delay: number}) => {
  const show = progress(frame, delay, 22, easeSnap);
  return (
    <div
      style={{
        opacity: show,
        transform: `translateY(${interpolate(show, [0, 1], [32, 0])}px)`,
        width: 355,
        padding: '20px 24px',
        borderRadius: 26,
        background: 'linear-gradient(135deg, rgba(8,30,68,0.84), rgba(1,5,14,0.72))',
        border: '1px solid rgba(99,243,255,0.22)',
        boxShadow: '0 30px 120px rgba(0,0,0,0.38), inset 0 0 45px rgba(17,107,255,0.12)',
      }}
    >
      <div style={{fontFamily: techFont, color: C.cyan, fontSize: 15, letterSpacing: '0.2em', textTransform: 'uppercase'}}>
        {label}
      </div>
      <div style={{marginTop: 7, fontFamily: displayFont, color: C.white, fontSize: 52, lineHeight: 0.95, fontWeight: 900, letterSpacing: '-0.06em'}}>
        {value}
      </div>
    </div>
  );
};

const ProofGate = ({title, text, status, frame, delay}: {title: string; text: string; status: string; frame: number; delay: number}) => {
  const show = progress(frame, delay, 24, easeOut);
  const live = pulse(frame, delay, 8);
  return (
    <div
      style={{
        opacity: show,
        transform: `translate3d(${interpolate(show, [0, 1], [80, 0])}px, 0, 0)`,
        width: 730,
        padding: '26px 30px',
        borderRadius: 26,
        background: 'linear-gradient(135deg, rgba(7,29,62,0.86), rgba(2,6,15,0.86))',
        border: `1px solid rgba(99,243,255,${0.2 + live * 0.18})`,
        boxShadow: `0 28px 110px rgba(0,0,0,0.34), 0 0 ${22 + live * 34}px rgba(17,107,255,0.12)`,
      }}
    >
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
        <div style={{fontFamily: displayFont, fontSize: 50, lineHeight: 1, color: C.white, fontWeight: 900, letterSpacing: '-0.05em'}}>
          {title}
        </div>
        <div style={{fontFamily: techFont, color: C.teal, fontSize: 15, letterSpacing: '0.22em', textTransform: 'uppercase'}}>
          {status}
        </div>
      </div>
      <div style={{marginTop: 10, fontFamily: techFont, color: C.soft, fontSize: 22, lineHeight: 1.24}}>
        {text}
      </div>
    </div>
  );
};

const AudioBars = ({bottom = 54}: {bottom?: number}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        left: 105,
        right: 105,
        bottom,
        height: 70,
        display: 'flex',
        alignItems: 'flex-end',
        gap: 7,
        opacity: 0.62,
      }}
    >
      {Array.from({length: 72}).map((_, i) => {
        const live = pulse(frame, i * 3, 4.8 + (i % 5) * 0.5);
        const wave = Math.sin(frame / 5 + i * 0.47) * 0.5 + 0.5;
        const h = 8 + wave * 18 + live * (i % 6 === 0 ? 58 : 24);
        return (
          <div
            key={i}
            style={{
              flex: 1,
              height: h,
              borderRadius: 999,
              background: `linear-gradient(180deg, ${i % 8 === 0 ? C.white : C.cyan}, rgba(17,107,255,0.08))`,
              boxShadow: `0 0 ${10 + live * 26}px rgba(99,243,255,0.38)`,
              opacity: 0.12 + live * 0.65,
            }}
          />
        );
      })}
    </div>
  );
};

const ColdOpen = ({launchLine}: TrailerProps) => {
  const frame = useCurrentFrame();
  const warning = progress(frame, 8, 26, easeOut) * fadeOut(frame, 88, 18);
  return (
    <AbsoluteFill style={{opacity: sceneOpacity(frame, 144)}}>
      <CinematicBase intensity={1.1} />
      <Sweep strong={1.1} />
      <MarketTape frame={frame} y={925} />
      <div style={{position: 'absolute', left: 116, top: 210}}>
        <Reveal frame={frame} delay={8}>
          <Kicker>{launchLine}</Kicker>
        </Reveal>
        <div style={{marginTop: 34, opacity: warning}}>
          <WordReveal text="LE MARCHÉ NE PRÉVIENT PAS." frame={frame} delay={22} size={118} />
        </div>
        <Reveal frame={frame} delay={98}>
          <MassiveTitle size={132}>Core Equity</MassiveTitle>
        </Reveal>
        <Reveal frame={frame} delay={118}>
          <Body width={760}>Un système pensé pour voir les mouvements importants avant qu'ils deviennent évidents.</Body>
        </Reveal>
      </div>
      <Orb variant="hero" />
      <CutFlash start={130} />
      <CinemaBars />
    </AbsoluteFill>
  );
};

const DiscoveryScene = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{opacity: sceneOpacity(frame, 196)}}>
      <CinematicBase intensity={1.25} />
      <FlowNetwork />
      <div style={{position: 'absolute', left: 116, top: 128, width: 780}}>
        <Reveal frame={frame}>
          <Kicker>Détection</Kicker>
        </Reveal>
        <Reveal frame={frame} delay={16}>
          <MassiveTitle size={104}>Repérer ce que la foule ne voit pas encore.</MassiveTitle>
        </Reveal>
        <Reveal frame={frame} delay={42}>
          <Body width={720}>
            Core Equity analyse les flux, les pools, les wallets et les répétitions qui peuvent annoncer un mouvement.
          </Body>
        </Reveal>
      </div>
      <div style={{position: 'absolute', left: 116, bottom: 136, display: 'flex', gap: 18}}>
        <StatPill frame={frame} delay={68} label="observe" value="flux" />
        <StatPill frame={frame} delay={80} label="compare" value="preuves" />
        <StatPill frame={frame} delay={92} label="filtre" value="bruit" />
      </div>
      <Sweep delay={55} strong={0.75} />
      <CutFlash start={176} />
      <CinemaBars />
    </AbsoluteFill>
  );
};

const ManipulationScene = () => {
  const frame = useCurrentFrame();
  const signals = [
    ['Flux anormaux', 'argent qui arrive trop vite'],
    ['Wallets actifs', 'comportements qui se répètent'],
    ['Pools sensibles', 'liquidité qui change de main'],
    ['Risque visible', 'pistes faibles bloquées'],
  ];
  return (
    <AbsoluteFill style={{opacity: sceneOpacity(frame, 204)}}>
      <CinematicBase intensity={1.45} />
      <Radar />
      <div style={{position: 'absolute', left: 116, top: 150}}>
        <Reveal frame={frame}>
          <Kicker>Manipulation radar</Kicker>
        </Reveal>
        <Reveal frame={frame} delay={16}>
          <MassiveTitle size={102}>Trouver les zones où l'argent se regroupe.</MassiveTitle>
        </Reveal>
        <Reveal frame={frame} delay={38}>
          <Body width={740}>Pas pour suivre le bruit. Pour comprendre la mécanique avant que le marché ne réagisse.</Body>
        </Reveal>
      </div>
      <div style={{position: 'absolute', left: 116, top: 590, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16}}>
        {signals.map(([title, text], i) => {
          const show = progress(frame, 62 + i * 8, 22, easeOut);
          return (
            <div
              key={title}
              style={{
                opacity: show,
                transform: `translateY(${interpolate(show, [0, 1], [35, 0])}px)`,
                width: 430,
                padding: '20px 24px',
                borderRadius: 22,
                background: 'linear-gradient(135deg, rgba(8,34,78,0.78), rgba(2,8,18,0.7))',
                border: '1px solid rgba(99,243,255,0.18)',
              }}
            >
              <div style={{fontFamily: displayFont, color: C.white, fontWeight: 900, fontSize: 38, letterSpacing: '-0.05em'}}>{title}</div>
              <div style={{fontFamily: techFont, color: C.soft, fontSize: 19, marginTop: 6}}>{text}</div>
            </div>
          );
        })}
      </div>
      <CutFlash start={182} />
      <CinemaBars />
    </AbsoluteFill>
  );
};

const ProofScene = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{opacity: sceneOpacity(frame, 204)}}>
      <CinematicBase intensity={1.35} />
      <FlowNetwork compact />
      <div style={{position: 'absolute', left: 116, top: 132}}>
        <Reveal frame={frame}>
          <Kicker color={C.amber}>Preuve avant action</Kicker>
        </Reveal>
        <Reveal frame={frame} delay={18}>
          <MassiveTitle size={100}>Aucune piste ne passe sans preuve.</MassiveTitle>
        </Reveal>
      </div>
      <div style={{position: 'absolute', left: 116, top: 390, display: 'grid', gap: 18}}>
        <ProofGate frame={frame} delay={44} title="Source" text="Une piste doit expliquer d'où vient la preuve." status="vérifiée" />
        <ProofGate frame={frame} delay={58} title="Route" text="Le système distingue observation, preuve et action réelle." status="contrôlée" />
        <ProofGate frame={frame} delay={72} title="Risque" text="Si la preuve est faible, le système bloque au lieu d'inventer." status="protégé" />
      </div>
      <Orb variant="mark" />
      <Sweep delay={20} strong={0.9} />
      <CutFlash start={183} />
      <CinemaBars />
    </AbsoluteFill>
  );
};

const AutonomyScene = () => {
  const frame = useCurrentFrame();
  const steps = [
    ['Observer', 'collecter plus de data utile'],
    ['Apprendre', 'comparer les résultats'],
    ['Simuler', 'tester sans argent réel'],
    ['Contrôler', 'agir seulement sous limites'],
  ];
  return (
    <AbsoluteFill style={{opacity: sceneOpacity(frame, 216)}}>
      <CinematicBase intensity={1.5} />
      <div style={{position: 'absolute', left: 116, top: 150, width: 780}}>
        <Reveal frame={frame}>
          <Kicker>Automatisation contrôlée</Kicker>
        </Reveal>
        <Reveal frame={frame} delay={16}>
          <MassiveTitle size={100}>Une IA qui progresse sans devenir dangereuse.</MassiveTitle>
        </Reveal>
        <Reveal frame={frame} delay={40}>
          <Body width={820}>D'abord la donnée. Ensuite la simulation. Puis seulement des décisions encadrées par le risque.</Body>
        </Reveal>
      </div>
      <div style={{position: 'absolute', right: 145, top: 165, width: 620, height: 680}}>
        {steps.map(([title, text], i) => {
          const show = progress(frame, 54 + i * 13, 24, easeSnap);
          const y = i * 142;
          return (
            <div key={title}>
              <div
                style={{
                  position: 'absolute',
                  left: 0,
                  top: y,
                  width: 86,
                  height: 86,
                  borderRadius: '50%',
                  border: '1px solid rgba(99,243,255,0.35)',
                  background: 'radial-gradient(circle, rgba(99,243,255,0.24), rgba(17,107,255,0.08), transparent)',
                  opacity: show,
                  transform: `scale(${0.75 + show * 0.25})`,
                  boxShadow: '0 0 50px rgba(99,243,255,0.22)',
                }}
              >
                <div style={{fontFamily: techFont, color: C.white, fontSize: 24, fontWeight: 900, textAlign: 'center', lineHeight: '86px'}}>
                  {i + 1}
                </div>
              </div>
              {i < steps.length - 1 && (
                <div
                  style={{
                    position: 'absolute',
                    left: 42,
                    top: y + 86,
                    width: 2,
                    height: 52 * show,
                    background: 'linear-gradient(180deg, rgba(99,243,255,0.7), rgba(17,107,255,0.05))',
                  }}
                />
              )}
              <div
                style={{
                  position: 'absolute',
                  left: 116,
                  top: y + 4,
                  width: 480,
                  opacity: show,
                  transform: `translateX(${interpolate(show, [0, 1], [52, 0])}px)`,
                }}
              >
                <div style={{fontFamily: displayFont, color: C.white, fontSize: 58, lineHeight: 0.95, fontWeight: 900, letterSpacing: '-0.06em'}}>
                  {title}
                </div>
                <div style={{marginTop: 8, fontFamily: techFont, color: C.soft, fontSize: 22}}>
                  {text}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <AudioBars bottom={46} />
      <CutFlash start={196} />
      <CinemaBars />
    </AbsoluteFill>
  );
};

const FinalReveal = () => {
  const frame = useCurrentFrame();
  const enter = progress(frame, 0, 55, easeSnap);
  const glow = pulse(frame, 0, 5.5);
  const line = progress(frame, 112, 52, easeInOut);
  return (
    <AbsoluteFill>
      <CinematicBase intensity={1.75} />
      <Sweep delay={0} strong={1.25} />
      <Orb variant="center" />
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: 485,
          textAlign: 'center',
          opacity: enter,
          transform: `translateY(${interpolate(enter, [0, 1], [50, 0])}px) scale(${0.96 + enter * 0.04})`,
        }}
      >
        <div style={{fontFamily: techFont, color: C.cyan, fontSize: 25, fontWeight: 900, letterSpacing: '0.52em', textTransform: 'uppercase'}}>
          La semaine prochaine
        </div>
        <div
          style={{
            marginTop: 28,
            fontFamily: displayFont,
            color: C.white,
            fontSize: 148,
            lineHeight: 0.86,
            letterSpacing: '-0.085em',
            fontWeight: 900,
            textShadow: `0 0 ${70 + glow * 78}px rgba(99,243,255,0.65), 0 20px 120px rgba(17,107,255,0.58)`,
          }}
        >
          Core Equity
        </div>
        <div
          style={{
            margin: '34px auto 0',
            width: 950,
            fontFamily: techFont,
            color: C.soft,
            fontSize: 34,
            lineHeight: 1.22,
            letterSpacing: '-0.02em',
          }}
        >
          Voir avant. Comprendre mieux. Agir avec contrôle.
        </div>
        <div
          style={{
            margin: '42px auto 0',
            width: 880 * line,
            height: 4,
            background: 'linear-gradient(90deg, transparent, #63f3ff, #116bff, transparent)',
            boxShadow: '0 0 42px rgba(99,243,255,0.95)',
          }}
        />
      </div>
      <MarketTape frame={frame} y={895} />
      <AudioBars bottom={38} />
      <CinemaBars />
    </AbsoluteFill>
  );
};

export const CoreEquityTrailer: React.FC<TrailerProps> = ({launchLine}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const audioFade = (audioFrame: number) => {
    const intro = interpolate(audioFrame, [0, fps * 1.1], [0, 0.98], clamp);
    const outro = interpolate(audioFrame, [durationInFrames - fps * 2.8, durationInFrames - fps * 0.15], [0.98, 0], clamp);
    return Math.min(intro, outro);
  };
  const flashIn = interpolate(frame, [0, 10], [1, 0], clamp);
  const flashOut = interpolate(frame, [durationInFrames - 18, durationInFrames], [0, 1], clamp);

  return (
    <AbsoluteFill style={{backgroundColor: C.black}}>
      <Audio
        src={staticFile('core-equity-cinematic-score.wav')}
        volume={audioFade}
      />
      <Sequence from={0} durationInFrames={170}>
        <ColdOpen launchLine={launchLine} />
      </Sequence>
      <Sequence from={145} durationInFrames={220}>
        <DiscoveryScene />
      </Sequence>
      <Sequence from={330} durationInFrames={230}>
        <ManipulationScene />
      </Sequence>
      <Sequence from={535} durationInFrames={230}>
        <ProofScene />
      </Sequence>
      <Sequence from={745} durationInFrames={240}>
        <AutonomyScene />
      </Sequence>
      <Sequence from={955} durationInFrames={305}>
        <FinalReveal />
      </Sequence>
      <TrailerHud />
      <ImpactWord at={146} word="VOIR" sub="avant le bruit" />
      <ImpactWord at={331} word="DÉTECTER" sub="les zones anormales" />
      <ImpactWord at={536} word="PROUVER" sub="avant chaque action" />
      <ImpactWord at={746} word="CONTRÔLER" sub="automatisation sous limites" />
      <AbsoluteFill
        style={{
          pointerEvents: 'none',
          opacity: Math.max(flashIn, flashOut),
          background: C.white,
        }}
      />
    </AbsoluteFill>
  );
};
