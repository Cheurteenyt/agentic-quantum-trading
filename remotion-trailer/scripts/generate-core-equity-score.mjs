import {writeFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const outPath = resolve(__dirname, '..', 'public', 'core-equity-cinematic-score.wav');

const sampleRate = 48000;
const duration = 42;
const channels = 2;
const total = Math.floor(sampleRate * duration);
const left = new Float32Array(total);
const right = new Float32Array(total);

let seed = 1337;
const rand = () => {
  seed = (seed * 1664525 + 1013904223) >>> 0;
  return seed / 0xffffffff;
};

const clamp = (v, min = -1, max = 1) => Math.max(min, Math.min(max, v));
const smooth = (x) => x * x * (3 - 2 * x);
const sine = (hz, t) => Math.sin(Math.PI * 2 * hz * t);
const tri = (hz, t) => 2 * Math.abs(2 * ((t * hz) % 1) - 1) - 1;
const saw = (hz, t) => 2 * ((t * hz) % 1) - 1;

const add = (i, mono, pan = 0, gain = 1) => {
  const l = Math.cos((pan + 1) * Math.PI * 0.25) * mono * gain;
  const r = Math.sin((pan + 1) * Math.PI * 0.25) * mono * gain;
  left[i] += l;
  right[i] += r;
};

const addTone = ({start, length, freq, gain, pan = 0, type = 'sine', attack = 0.02, release = 0.4}) => {
  const s0 = Math.max(0, Math.floor(start * sampleRate));
  const s1 = Math.min(total, Math.floor((start + length) * sampleRate));
  for (let i = s0; i < s1; i++) {
    const t = i / sampleRate;
    const local = t - start;
    const envIn = Math.min(1, local / attack);
    const envOut = Math.min(1, (length - local) / release);
    const env = smooth(clamp(Math.min(envIn, envOut), 0, 1));
    const osc =
      type === 'saw'
        ? saw(freq, t) * 0.58 + sine(freq * 0.5, t) * 0.42
        : type === 'tri'
          ? tri(freq, t)
          : sine(freq, t);
    add(i, osc * env, pan, gain);
  }
};

const addKick = (time, gain = 1) => {
  const len = 0.55;
  const s0 = Math.floor(time * sampleRate);
  const s1 = Math.min(total, Math.floor((time + len) * sampleRate));
  for (let i = s0; i < s1; i++) {
    const t = i / sampleRate - time;
    const env = Math.exp(-t * 8.5);
    const f = 88 * Math.exp(-t * 9) + 36;
    const click = t < 0.012 ? (rand() * 2 - 1) * (1 - t / 0.012) : 0;
    add(i, (sine(f, t) * env + click * 0.22) * gain, 0, 0.82);
  }
};

const addTick = (time, pan = 0, gain = 1) => {
  const len = 0.06;
  const s0 = Math.floor(time * sampleRate);
  const s1 = Math.min(total, Math.floor((time + len) * sampleRate));
  for (let i = s0; i < s1; i++) {
    const t = i / sampleRate - time;
    const env = Math.exp(-t * 44);
    add(i, (rand() * 2 - 1) * env, pan, gain * 0.28);
  }
};

const addImpact = (time, gain = 1.0) => {
  const len = 2.3;
  const s0 = Math.floor(time * sampleRate);
  const s1 = Math.min(total, Math.floor((time + len) * sampleRate));
  for (let i = s0; i < s1; i++) {
    const t = i / sampleRate - time;
    const low = sine(42 - t * 7, t) * Math.exp(-t * 1.65);
    const mid = sine(83, t) * Math.exp(-t * 3.2);
    const noise = (rand() * 2 - 1) * Math.exp(-t * 5.6);
    add(i, (low * 0.95 + mid * 0.24 + noise * 0.18) * gain, 0, 1);
  }
};

const addWhoosh = (start, length, gain = 1, pan = 0) => {
  const s0 = Math.max(0, Math.floor(start * sampleRate));
  const s1 = Math.min(total, Math.floor((start + length) * sampleRate));
  for (let i = s0; i < s1; i++) {
    const t = i / sampleRate - start;
    const x = t / length;
    const env = smooth(x) * (1 - smooth(Math.max(0, x - 0.78) / 0.22));
    const sweep = sine(180 + x * 1800, t) * 0.25 + (rand() * 2 - 1) * 0.75;
    add(i, sweep * env * gain, pan + Math.sin(x * Math.PI * 2) * 0.25, 0.4);
  }
};

const addRiser = (start, length, gain = 1) => {
  const s0 = Math.max(0, Math.floor(start * sampleRate));
  const s1 = Math.min(total, Math.floor((start + length) * sampleRate));
  for (let i = s0; i < s1; i++) {
    const t = i / sampleRate - start;
    const x = t / length;
    const env = smooth(x);
    const f = 120 + x * x * 1150;
    const texture = sine(f, t) * 0.35 + tri(f * 0.5, t) * 0.18 + (rand() * 2 - 1) * 0.18;
    add(i, texture * env * gain, Math.sin(x * Math.PI * 2) * 0.5, 0.36);
  }
};

const addPad = () => {
  const notes = [36.71, 55.0, 73.42, 110.0];
  for (let i = 0; i < total; i++) {
    const t = i / sampleRate;
    const intro = smooth(Math.min(1, t / 6));
    const outro = smooth(Math.min(1, (duration - t) / 4));
    const env = intro * outro;
    const build = 0.22 + smooth(Math.min(1, t / duration)) * 0.42;
    const tone =
      sine(notes[0], t) * 0.42 +
      sine(notes[1], t + 0.01) * 0.22 +
      tri(notes[2], t * 0.5) * 0.1 +
      saw(notes[3], t * 0.25) * 0.04;
    add(i, tone * env * build, Math.sin(t * 0.12) * 0.18, 0.25);
  }
};

const bpm = 92;
const beat = 60 / bpm;
const chordRoots = [36.71, 43.65, 32.7, 49.0];

addPad();

for (let b = 0; b < Math.floor(duration / beat); b++) {
  const t = b * beat;
  const section = Math.floor(t / 8);
  const root = chordRoots[section % chordRoots.length];
  if (t > 3.8) {
    addKick(t, t > 24 ? 0.95 : 0.72);
  }
  if (t > 8 && b % 2 === 1) {
    addKick(t + beat * 0.5, 0.34);
  }
  if (t > 10 && b % 2 === 0) {
    addTick(t + beat * 0.72, b % 4 ? 0.55 : -0.45, 0.8);
  }
  if (t > 6) {
    addTone({start: t, length: beat * 1.7, freq: root, gain: 0.15 + Math.min(0.18, t / 160), type: 'saw', attack: 0.01, release: 0.22});
  }
  if (t > 12 && b % 1 === 0) {
    const arp = [root * 2, root * 2.5, root * 3, root * 4][b % 4];
    addTone({start: t + beat * 0.25, length: 0.16, freq: arp, gain: 0.08, pan: b % 2 ? 0.35 : -0.35, type: 'tri', attack: 0.005, release: 0.05});
  }
}

const cuts = [4.87, 11.03, 17.87, 24.87, 31.83];
for (const cut of cuts) {
  addRiser(cut - 1.85, 1.8, 0.65);
  addWhoosh(cut - 0.7, 0.78, 0.85);
  addImpact(cut, cut === 31.83 ? 1.25 : 1.0);
}

addImpact(0.35, 0.62);
addRiser(36.5, 3.2, 0.42);
addTone({start: 32.2, length: 7.6, freq: 55, gain: 0.23, type: 'sine', attack: 0.4, release: 2.5});
addTone({start: 33.1, length: 6.8, freq: 110, gain: 0.1, pan: 0.22, type: 'tri', attack: 0.4, release: 2.2});

let peak = 0;
for (let i = 0; i < total; i++) {
  peak = Math.max(peak, Math.abs(left[i]), Math.abs(right[i]));
}
const normalizer = peak > 0 ? 0.92 / peak : 1;

const dataSize = total * channels * 2;
const buffer = Buffer.alloc(44 + dataSize);
buffer.write('RIFF', 0);
buffer.writeUInt32LE(36 + dataSize, 4);
buffer.write('WAVE', 8);
buffer.write('fmt ', 12);
buffer.writeUInt32LE(16, 16);
buffer.writeUInt16LE(1, 20);
buffer.writeUInt16LE(channels, 22);
buffer.writeUInt32LE(sampleRate, 24);
buffer.writeUInt32LE(sampleRate * channels * 2, 28);
buffer.writeUInt16LE(channels * 2, 32);
buffer.writeUInt16LE(16, 34);
buffer.write('data', 36);
buffer.writeUInt32LE(dataSize, 40);

let offset = 44;
for (let i = 0; i < total; i++) {
  const t = i / sampleRate;
  const masterFadeIn = smooth(Math.min(1, t / 0.9));
  const masterFadeOut = smooth(Math.min(1, (duration - t) / 2.2));
  const master = masterFadeIn * masterFadeOut * normalizer;
  buffer.writeInt16LE(Math.round(clamp(left[i] * master) * 32767), offset);
  offset += 2;
  buffer.writeInt16LE(Math.round(clamp(right[i] * master) * 32767), offset);
  offset += 2;
}

writeFileSync(outPath, buffer);
console.log(`Generated ${outPath}`);
