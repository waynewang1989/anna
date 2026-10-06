#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
圆球秘境 · 寻宝  (Round World: Treasure Hunt)
---------------------------------------------
一个用 Python + ursina 写的第三人称视角 3D 寻宝小游戏。

世界设定:
  * 地面由一颗颗紫色纯圆小球铺成;
  * 玩家可以按 F 在 地面 / 地下洞穴 之间穿梭;
  * 宝藏分布在 天上(浮空平台)、地面、地下洞穴 三处;
  * 地上有妖怪随机游荡(不会追人也不会伤人), 用主人公的"圆头剑"(剑尖是一颗圆球)攻击,
    击中数次后妖怪消失;
  * 没有血条, 玩家不会受伤; 集齐全部宝藏即胜利。

操作(第三人称):
  鼠标        转动镜头(绕角色环视)
  W / S       前进 / 后退      A / D 左移 / 右移      Shift 奔跑
  空格        跳跃 / 二段跳(二段跳更高)
  左键 / J    挥剑攻击
  F           下潜进入地下 / 从地下上浮(穿梭)
  P / Esc     暂停 / 继续     R 重新开始     Q 退出游戏

运行:  .venv/bin/python game.py
"""

import math
import os
import random
import struct
import sys
import threading
import wave

from ursina import *
from ursina import mesh_importer
from PIL import Image, ImageDraw, ImageFilter, ImageFont

random.seed(20260926)

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
SOUND_DIR = os.path.join(GAME_DIR, 'assets', 'sounds')
os.makedirs(SOUND_DIR, exist_ok=True)
SELFTEST = os.environ.get('RW_SELFTEST', '') not in ('', '0')

# ----------------------------------------------------------------------------
# 调色板
# ----------------------------------------------------------------------------
PURPLE      = (0.60, 0.28, 0.92)
PURPLE_DARK = (0.34, 0.14, 0.58)
PURPLE_DEEP = (0.16, 0.07, 0.30)
GOLD        = (1.00, 0.78, 0.25)
CYAN        = (0.35, 0.90, 1.00)
SKIN        = (1.00, 0.80, 0.62)
TUNIC       = (0.20, 0.55, 0.85)
RED         = (0.95, 0.25, 0.30)
GREEN       = (0.45, 0.85, 0.35)
BROWN       = (0.45, 0.30, 0.18)
STEEL       = (0.85, 0.90, 1.00)


def col(rgb, a=1.0):
    return Color(rgb[0], rgb[1], rgb[2], a)


def tinted(rgb, amount):
    return Color(min(1, rgb[0] + amount), min(1, rgb[1] + amount),
                 min(1, rgb[2] + amount), 1.0)


def lerp_angle(a, b, t):
    """角度最短路径插值 (a, b 为弧度)"""
    d = (b - a + math.pi) % math.tau - math.pi
    return a + d * t


# ----------------------------------------------------------------------------
# 程序化音效 (标准库合成 WAV, 无需外部资源)
# ----------------------------------------------------------------------------
SR = 22050


def _tone(freq, dur, kind='sine', vol=0.4, sweep_to=None, delay=0.0, vib=0.0):
    n = int(dur * SR)
    out = [0.0] * n
    for i in range(n):
        t = i / SR
        f = freq if sweep_to is None else freq + (sweep_to - freq) * (i / n)
        ph = 2 * math.pi * f * t
        if vib:
            ph += vib * math.sin(2 * math.pi * 6 * t)
        if kind == 'sine':
            v = math.sin(ph)
        elif kind == 'tri':
            v = 2 / math.pi * math.asin(math.sin(ph))
        elif kind == 'saw':
            v = 2 * ((f * t) % 1.0) - 1
        else:  # square
            v = 1.0 if math.sin(ph) >= 0 else -1.0
        env = min(1.0, t / 0.008) * math.exp(-3.2 * t / max(dur, 1e-6))
        out[i] = v * vol * env
    return out, delay


def _noise(dur, vol=0.3, decay=6.0, delay=0.0, lp=0.5):
    n = int(dur * SR)
    out, prev = [0.0] * n, 0.0
    for i in range(n):
        t = i / SR
        w = random.uniform(-1, 1)
        prev = prev * (1 - lp) + w * lp
        out[i] = prev * vol * math.exp(-decay * t)
    return out, delay


def _loop_noise(dur, vol=0.8, lp=0.30, hp=0.0, lfo_hz=0.0, lfo_depth=0.0):
    """可无缝循环的环境底噪: 雨声 / 风声 / 雪夜微响 (纯标准库合成)"""
    n = max(64, int(dur * SR))
    out, lo, hi = [0.0] * n, 0.0, 0.0
    for i in range(n):
        w = random.uniform(-1, 1)
        lo = lo * (1 - lp) + w * lp                 # 一阶低通
        v = lo
        if hp:
            hi = hi * (1 - hp) + v * hp             # 再去掉过低频的隆隆声
            v = v - hi
        out[i] = v
    if lfo_hz > 0:
        cyc = max(1, int(round(lfo_hz * dur)))      # 取整数周期, 保证首尾相接
        for i in range(n):
            out[i] *= 1.0 - lfo_depth * (0.5 + 0.5 * math.sin(math.tau * cyc * i / n))
    xf = max(1, int(min(0.55, dur * 0.22) * SR))    # 尾部淡入头部 -> 无缝循环
    for i in range(xf):
        f = i / xf
        out[n - xf + i] = out[n - xf + i] * (1 - f) + out[i] * f
    peak = max(1e-6, max(abs(v) for v in out))
    return [v * 0.92 * vol / peak for v in out]


def _thunder():
    """一声闷雷: 高频炸裂 + 低频隆隆余音"""
    n = int(2.4 * SR)
    out, lo = [0.0] * n, 0.0
    for i in range(n):
        t = i / SR
        w = random.uniform(-1, 1)
        lo = lo * 0.985 + w * 0.015
        crack = math.exp(-22 * t) * w
        rumble = math.exp(-1.35 * t) * lo * 9.0
        out[i] = (crack * 0.5 + rumble) * min(1.0, t / 0.015)
    peak = max(1e-6, max(abs(v) for v in out))
    return [v * 0.95 / peak for v in out], 0.0      # (samples, delay) 同 _tone/_noise


def _mix(tracks, total=None):
    length = max(len(s) + int(d * SR) for s, d in tracks)
    if total:
        length = max(length, int(total * SR))
    buf = [0.0] * length
    for s, d in tracks:
        off = int(d * SR)
        for i, v in enumerate(s):
            buf[off + i] += v
    peak = max(1e-6, max(abs(v) for v in buf))
    k = 0.92 / peak
    return [max(-1, min(1, v * k)) for v in buf]


def _write_wav(path, data):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b''.join(struct.pack('<h', int(v * 32000)) for v in data))


SFX_DEF = {
    'jump':   lambda: [_tone(300, 0.18, 'sine', 0.5, 620)],
    'djump':  lambda: [_tone(420, 0.16, 'sine', 0.45, 860)],
    'swing':  lambda: [_noise(0.16, 0.5, 9.0, lp=0.25), _tone(820, 0.14, 'tri', 0.18, 260)],
    'hit':    lambda: [_tone(170, 0.10, 'square', 0.5), _noise(0.07, 0.4, 12.0)],
    'die':    lambda: [_tone(520, 0.42, 'saw', 0.35, 70), _noise(0.25, 0.35, 7.0)],
    'gem':    lambda: [_tone(880, 0.5, 'sine', 0.35), _tone(1174, 0.45, 'sine', 0.3, delay=0.09),
                       _tone(1568, 0.55, 'sine', 0.28, delay=0.18)],
    'dive':   lambda: [_tone(520, 0.38, 'sine', 0.45, 110), _tone(300, 0.08, 'sine', 0.25, delay=0.30),
                       _tone(420, 0.08, 'sine', 0.22, delay=0.40)],
    'rise':   lambda: [_tone(140, 0.40, 'sine', 0.45, 620), _tone(700, 0.10, 'sine', 0.2, delay=0.36)],
    'bounce': lambda: [_tone(170, 0.34, 'sine', 0.5, 760), _tone(760, 0.16, 'sine', 0.3, 240, delay=0.20)],
    'break':  lambda: [_noise(0.14, 0.5, 8.0), _tone(240, 0.10, 'square', 0.3, 120)],
    'win':    lambda: [_tone(f, 0.5, 'tri', 0.35, delay=i * 0.14) for i, f in enumerate((523, 659, 784, 1046))],
    'lose':   lambda: [_tone(f, 0.55, 'tri', 0.35, delay=i * 0.20) for i, f in enumerate((392, 330, 262, 196))],
    'ui':     lambda: [_tone(700, 0.07, 'sine', 0.35)],
    'thunder': lambda: [_thunder()],
}

# 可无缝循环的天气环境音 (雨 / 风 / 雪), 由 WeatherSystem 交叉淡入淡出
LOOP_DEF = {
    'rain': lambda: _loop_noise(4.0, 1.00, lp=0.34, hp=0.035),
    'wind': lambda: _loop_noise(6.0, 1.00, lp=0.055, lfo_hz=0.34, lfo_depth=0.62),
    'snow': lambda: _loop_noise(5.0, 0.62, lp=0.48, hp=0.020, lfo_hz=0.20, lfo_depth=0.30),
}


def build_sounds():
    paths = {}
    for name, fn in SFX_DEF.items():
        p = os.path.join(SOUND_DIR, name + '.wav')
        if not os.path.exists(p):
            _write_wav(p, _mix(fn()))
        paths[name] = p
    for name, fn in LOOP_DEF.items():
        p = os.path.join(SOUND_DIR, name + '.wav')
        if not os.path.exists(p):
            _write_wav(p, fn())          # 循环底噪已自行归一化, 不再过 _mix
        paths[name] = p
    p = os.path.join(SOUND_DIR, 'music.wav')
    if not os.path.exists(p):
        _write_wav(p, _make_music())
    paths['music'] = p
    return paths


def _make_music():
    """12 秒循环的轻柔氛围音乐: 和弦垫 + 零星铃音。"""
    dur = 12.0
    n = int(dur * SR)
    buf = [0.0] * n
    chords = [(220.0, 261.6, 329.6), (174.6, 220.0, 261.6),
              (196.0, 246.9, 293.7), (164.8, 196.0, 246.9)]
    for ci, ch in enumerate(chords):
        t0 = ci * 3.0
        for f in ch:
            for i in range(int(3.0 * SR)):
                t = i / SR
                g = t0 + t
                idx = int(g * SR)
                if idx >= n:
                    break
                env = min(1, t / 0.6) * min(1, (3.0 - t) / 0.8)
                buf[idx] += 0.055 * env * (math.sin(2 * math.pi * f * t)
                                           + 0.4 * math.sin(2 * math.pi * f * 2 * t))
    bells = [(0.5, 880), (2.2, 1046), (4.1, 784), (6.0, 880), (7.6, 1174), (9.4, 988), (11.0, 1318)]
    for t0, f in bells:
        for i in range(int(1.2 * SR)):
            t = i / SR
            idx = int((t0 + t) * SR) % n
            buf[idx] += 0.10 * math.exp(-3.5 * t) * math.sin(2 * math.pi * f * t)
    peak = max(1e-6, max(abs(v) for v in buf))
    return [v * 0.9 / peak for v in buf]


# ----------------------------------------------------------------------------
# 中文字体 & PIL 文字贴图 (HUD / 面板)
# ----------------------------------------------------------------------------
FONT_PATH = None
for fp in ('/System/Library/Fonts/PingFang.ttc',
           '/System/Library/Fonts/Hiragino Sans GB.ttc',
           '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
           '/System/Library/Fonts/STHeiti Medium.ttc',
           'C:/Windows/Fonts/msyh.ttc',
           '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc'):
    if os.path.exists(fp):
        FONT_PATH = fp
        break
_font_cache = {}


def get_font(size, bold=False):
    key = (size, bold)
    if key not in _font_cache:
        if FONT_PATH:
            try:
                _font_cache[key] = ImageFont.truetype(FONT_PATH, size, index=1 if bold else 0)
            except Exception:
                _font_cache[key] = ImageFont.truetype(FONT_PATH, size)
        else:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def text_image(lines, pad=18, line_gap=10, align='left', bg=None, stroke=3):
    """lines: [(text, size, (r,g,b,a)), ...]  返回 PIL RGBA 图像"""
    fonts = [get_font(s) for _, s, _ in lines]
    widths, heights = [], []
    for (t, s, _c), f in zip(lines, fonts):
        box = f.getbbox(t)
        widths.append(box[2] - box[0] + stroke * 2)
        heights.append(box[3] - box[1])
    w = max(widths) + pad * 2
    h = sum(heights) + line_gap * (len(lines) - 1) + pad * 2
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if bg:
        d.rounded_rectangle([2, 2, w - 3, h - 3], radius=16, fill=bg)
    y = pad
    for (t, s, c), f, tw, th in zip(lines, fonts, widths, heights):
        if align == 'center':
            x = (w - tw) // 2
        elif align == 'right':
            x = w - pad - tw
        else:
            x = pad
        d.text((x + stroke, y + stroke), t, font=f, fill=(0, 0, 0, 200),
               stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
        d.text((x + stroke, y + stroke), t, font=f, fill=c)
        y += th + line_gap
    return img


class Pic(Entity):
    """aspect2d 上的贴图面板 (支持中文)"""

    def __init__(self, **kwargs):
        super().__init__(model='quad', parent=application.base.aspect2d,
                         transparency=True, **kwargs)
        self._img = None

    def set_image(self, img):
        self._img = img
        self.texture = Texture(img)
        px = 2.0 / max(1, int(window.size[1]))
        self.scale = (img.width * px, img.height * px)


# ----------------------------------------------------------------------------
# 程序化网格: 顶点色烘焙光照 (无需 shader / 灯光, 性能好)
# ----------------------------------------------------------------------------
LIGHT = Vec3(0.42, 0.85, 0.35).normalized()
VIEW = Vec3(0.18, -0.62, 0.76).normalized()
HALF = (LIGHT + VIEW).normalized()


def shade(n):
    """把法线烘焙成顶点色: 环境光 + 漫反射 + 高光 + 边缘光"""
    n = Vec3(*n).normalized()
    lam = max(n.dot(LIGHT), 0.0)
    spec = pow(max(n.dot(HALF), 0.0), 26) * 0.75
    rim = pow(1.0 - max(n.dot(VIEW), 0.0), 2.4) * 0.28
    amb = 0.40 + 0.20 * (n.y * 0.5 + 0.5)
    v = amb + 0.75 * lam
    return Color(min(1, v + spec + rim * 0.5), min(1, v + spec + rim * 0.5),
                 min(1, v + spec + rim), 1.0)


def sphere_data(radius=0.5, rings=10, sectors=16, yoff=0.0, voff=0):
    verts, tris, cols = [], [], []
    for r in range(rings + 1):
        phi = (r / rings) * math.pi
        for s in range(sectors + 1):
            th = (s / sectors) * math.tau
            n = (math.sin(phi) * math.cos(th), math.cos(phi), math.sin(phi) * math.sin(th))
            verts.append(Vec3(n[0] * radius, n[1] * radius + yoff, n[2] * radius))
            cols.append(shade(n))
    for r in range(rings):
        for s in range(sectors):
            a = voff + r * (sectors + 1) + s
            b = a + sectors + 1
            tris += [a, a + 1, b, b, a + 1, b + 1]
    return verts, tris, cols


def ball_mesh():
    """地面/墙体/平台小球: 纯圆球(光滑, 无凸点)"""
    v, t, c = sphere_data(0.5, 12, 20)
    return Mesh(vertices=v, triangles=t, colors=c, mode='triangle', static=True)


def box_mesh():
    v, t, c = [], [], []
    faces = [((0, 0, 1), [(1, 1, 1), (-1, 1, 1), (-1, -1, 1), (1, -1, 1)]),
             ((0, 0, -1), [(-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1)]),
             ((0, 1, 0), [(-1, 1, 1), (1, 1, 1), (1, 1, -1), (-1, 1, -1)]),
             ((0, -1, 0), [(1, -1, 1), (-1, -1, 1), (-1, -1, -1), (1, -1, -1)]),
             ((1, 0, 0), [(1, 1, -1), (1, 1, 1), (1, -1, 1), (1, -1, -1)]),
             ((-1, 0, 0), [(-1, 1, 1), (-1, 1, -1), (-1, -1, -1), (-1, -1, 1)])]
    for n, quad in faces:
        base = len(v)
        sc = shade(n)
        for p in quad:
            v.append(Vec3(p[0] * 0.5, p[1] * 0.5, p[2] * 0.5)); c.append(sc)
        t += [base, base + 1, base + 2, base, base + 2, base + 3]
    return Mesh(vertices=v, triangles=t, colors=c, mode='triangle', static=True)


def cone_mesh(seg=10, radius=0.5, height=1.0):
    v, t, c = [], [], []
    apex = 0
    v.append(Vec3(0, height * 0.5, 0)); c.append(shade((0, 1, 0)))
    for i in range(seg):
        a = i / seg * math.tau
        n = (math.cos(a), 0.45, math.sin(a))
        v.append(Vec3(math.cos(a) * radius, -height * 0.5, math.sin(a) * radius)); c.append(shade(n))
    for i in range(seg):
        t += [apex, 1 + (i + 1) % seg, 1 + i]
    bc = len(v)
    v.append(Vec3(0, -height * 0.5, 0)); c.append(shade((0, -1, 0)))
    for i in range(seg):
        t += [bc, 1 + i, 1 + (i + 1) % seg]
    return Mesh(vertices=v, triangles=t, colors=c, mode='triangle', static=True)


def gem_mesh():
    """菱形宝石"""
    v, t, c = [], [], []
    seg = 6
    top, bot = Vec3(0, 0.62, 0), Vec3(0, -0.62, 0)
    ring = []
    for i in range(seg):
        a = i / seg * math.tau
        ring.append(Vec3(math.cos(a) * 0.42, 0.08, math.sin(a) * 0.42))
    for i in range(seg):
        p0, p1 = ring[i], ring[(i + 1) % seg]
        n = ((p0 + p1) * 0.5 + Vec3(0, 0.4, 0))
        base = len(v)
        v += [top, p0, p1]; c += [shade(n)] * 3
        t += [base, base + 1, base + 2]
        n2 = ((p0 + p1) * 0.5 - Vec3(0, 0.4, 0))
        base = len(v)
        v += [bot, p1, p0]; c += [shade(n2)] * 3
        t += [base, base + 1, base + 2]
    return Mesh(vertices=v, triangles=t, colors=c, mode='triangle', static=True)


def ring_mesh(inner=0.55, outer=1.0, seg=24):
    v, t, c = [], [], []
    up = shade((0, 1, 0))
    for i in range(seg + 1):
        a = i / seg * math.tau
        v.append(Vec3(math.cos(a) * inner, 0, math.sin(a) * inner)); c.append(up)
        v.append(Vec3(math.cos(a) * outer, 0, math.sin(a) * outer)); c.append(up)
    for i in range(seg):
        a0, a1, b0, b1 = i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 3
        t += [a0, b0, b1, a0, b1, a1]
    return Mesh(vertices=v, triangles=t, colors=c, mode='triangle', static=True)


def slash_mesh():
    """挥剑的弧形刀光 (竖直扇环)"""
    v, t, c = [], [], []
    seg = 10
    a0, a1 = -1.15, 1.15
    for i in range(seg + 1):
        f = i / seg
        a = a0 + (a1 - a0) * f
        r_in, r_out = 0.55, 1.5 * (1.0 - 0.45 * abs(f - 0.5) * 2)
        v.append(Vec3(math.sin(a) * r_in, math.cos(a) * r_in, 0)); c.append(Color(1, 1, 1, 0.15))
        v.append(Vec3(math.sin(a) * r_out, math.cos(a) * r_out, 0)); c.append(Color(1, 1, 1, 0.9))
    for i in range(seg):
        a0i, a1i, b0i, b1i = i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 3
        t += [a0i, a1i, b1i, a0i, b1i, b0i]
    return Mesh(vertices=v, triangles=t, colors=c, mode='triangle', static=True)


def tube_mesh(seg=12):
    v, t, c = [], [], []
    for i in range(seg + 1):
        a = i / seg * math.tau
        v.append(Vec3(math.cos(a) * 0.5, -0.5, math.sin(a) * 0.5)); c.append(Color(1, 1, 1, 0.9))
        v.append(Vec3(math.cos(a) * 0.5, 0.5, math.sin(a) * 0.5)); c.append(Color(1, 1, 1, 0.15))
    for i in range(seg):
        a0, a1, b0, b1 = i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 3
        t += [a0, b0, b1, a0, b1, a1]
    return Mesh(vertices=v, triangles=t, colors=c, mode='triangle', static=True)


def sky_dome_mesh():
    """世界背景穹顶: 上半夜空渐变+星点, 下半洞穴暗色"""
    v, t, c = sphere_data(60.0, 22, 28)
    for i, p in enumerate(v):
        h = p.y / 60.0
        if h > 0.02:
            # 白天: 地平线浅蓝白 -> 天顶深蓝
            f = min(1, h * 1.25)
            base = (0.62 + (0.13 - 0.62) * f,
                    0.80 + (0.42 - 0.80) * f,
                    1.00 + (0.90 - 1.00) * f)
        else:
            f = min(1, -h * 2.2)
            base = (0.10 * (1 - f) + 0.05, 0.04 * (1 - f) + 0.02, 0.22 * (1 - f) + 0.10)
        cc = c[i]
        g = 0.62 + 0.55 * cc[0]          # 保留一点烘焙明暗, 整体是明亮白天
        c[i] = Color(min(1, base[0] * g), min(1, base[1] * g), min(1, base[2] * g), 1)
    return Mesh(vertices=v, triangles=t, colors=c, mode='triangle', static=True)


def register_meshes():
    mesh_importer.imported_meshes['rw_ball'] = ball_mesh()
    mesh_importer.imported_meshes['rw_sphere'] = Mesh(*sphere_data(0.5, 10, 16), mode='triangle', static=True)
    mesh_importer.imported_meshes['rw_sphere_lo'] = Mesh(*sphere_data(0.5, 7, 10), mode='triangle', static=True)
    mesh_importer.imported_meshes['rw_box'] = box_mesh()
    mesh_importer.imported_meshes['rw_cone'] = cone_mesh()
    mesh_importer.imported_meshes['rw_gem'] = gem_mesh()
    mesh_importer.imported_meshes['rw_ring'] = ring_mesh()
    mesh_importer.imported_meshes['rw_slash'] = slash_mesh()
    mesh_importer.imported_meshes['rw_tube'] = tube_mesh()
    mesh_importer.imported_meshes['rw_dome'] = sky_dome_mesh()


# ----------------------------------------------------------------------------
# 世界常量
# ----------------------------------------------------------------------------
SPACING = 1.15
SURF_N = 25                                      # 球阵边长: 场地比旧版更宽阔
SURF_HALF = (SURF_N - 1) / 2 * SPACING          # ~13.8
SURF_Y = 0.62                                    # 地面(球顶)站立高度
CAVE_Y = -7.2                                    # 洞穴更深, 给第三人称镜头留出空间
CAVE_G = CAVE_Y + 0.62
CAVE_CEIL = -1.9
CAVE_HALF = 11.5
GRAV = 24.0

# 布局放大系数: 场地半径相对旧版(10.35)放大了 WORLD_K 倍, 关卡坐标等比放大
WORLD_K = SURF_HALF / 10.35


def WK(v):
    """旧版关卡坐标 -> 新版(等比放大)"""
    return v * WORLD_K


PLATFORMS = [  # (x, z, top_y, half)
    (WK(2.5), WK(2.0), WK(3.2), WK(1.7)),
    (WK(5.6), WK(0.4), WK(5.4), WK(1.5)),
    (WK(8.0), WK(3.2), WK(7.6), WK(1.5)),
    (WK(6.0), WK(6.6), WK(9.8), WK(1.6)),
    (WK(2.0), WK(8.2), WK(12.0), WK(1.5)),
]
BOUNCE_POS = (WK(-6.5), WK(-6.5))

SKY_TREASURES = [(WK(5.6), WK(6.7), WK(0.4)), (WK(6.0), WK(11.1), WK(6.6)),
                 (WK(2.0), WK(13.3), WK(8.2)), (WK(-6.5), WK(10.6), WK(-6.5))]
GROUND_TREASURES = [(WK(-8.2), WK(6.4)), (WK(9.0), WK(-7.2)), (WK(0.5), WK(-9.6))]
CAVE_TREASURES = [(WK(-5.0), WK(-4.0)), (WK(4.2), WK(5.0)), (WK(-2.0), WK(6.4))]
CAVE_HIDDEN = [(WK(6.0), WK(-3.0)), (WK(-6.0), WK(2.0))]            # 藏在可破坏水晶里
SURF_HIDDEN = [(WK(-4.5), WK(8.5)), (WK(7.5), WK(5.5)), (WK(-8.5), WK(-3.0))]  # 地面土球(掉爱心)

TOTAL_TREASURE = len(SKY_TREASURES) + len(GROUND_TREASURES) + len(CAVE_TREASURES) + len(CAVE_HIDDEN)


# ----------------------------------------------------------------------------
# 粒子
# ----------------------------------------------------------------------------
class Particles:
    def __init__(self, n=150):
        self.items = []
        for _ in range(n):
            e = Entity(model='quad', billboard=True, color=color.white, scale=0.2,
                       transparency=True, texture=PART_TEX)
            e.enabled = False
            self.items.append({'e': e, 'vel': Vec3(0, 0, 0), 'life': 0.0, 'max': 1.0,
                               'g': 9.0, 'size': 0.2})

    def burst(self, pos, rgb, count=10, speed=5.0, life=0.6, size=0.22, g=9.0, up=2.0):
        made = 0
        for it in self.items:
            if made >= count:
                break
            if it['life'] > 0:
                continue
            made += 1
            e = it['e']
            e.enabled = True
            e.position = pos + Vec3(random.uniform(-.2, .2), random.uniform(-.2, .2), random.uniform(-.2, .2))
            e.color = col(rgb)
            d = Vec3(random.uniform(-1, 1), random.uniform(-0.2, 1) + up / speed, random.uniform(-1, 1)).normalized()
            it['vel'] = d * speed * random.uniform(0.5, 1.0)
            it['life'] = it['max'] = life * random.uniform(0.7, 1.3)
            it['g'] = g
            it['size'] = size * random.uniform(0.7, 1.3)
            e.scale = it['size']
            e.alpha = 1

    def update(self, dt=None):
        dt = time.dt if dt is None else dt
        for it in self.items:
            if it['life'] <= 0:
                continue
            it['life'] -= dt
            e = it['e']
            if it['life'] <= 0:
                e.enabled = False
                continue
            it['vel'].y -= it['g'] * dt
            e.position += it['vel'] * dt
            f = it['life'] / it['max']
            e.alpha = f
            e.scale = it['size'] * (0.4 + 0.6 * f)


# ----------------------------------------------------------------------------
# 天气系统: 晴天 / 下雨 / 下雪 / 刮风, 随机切换 + 平滑过渡
# ----------------------------------------------------------------------------
WX = None                       # WeatherSystem 实例, main() 里创建
FADE_QUAD = None                # 穿梭用的全屏淡黑遮罩, main() 里创建
WEATHER_ORDER = ['clear', 'rain', 'snow', 'wind']

# 天空表现约定: 任何天气都保持"蓝天白云"
#   sky       穹顶颜色倍率 —— 四种天气都接近 1.0, 蓝天渐变永远不变暗
#   sky_a     内层天空罩透明度 —— 恒为 0, 不再用色罩把天染成阴雨灰
#   clouds    云量 —— 恒为高值, cloud_col 恒为纯白, 白云在任何天气都看得见
#   tint_a    全屏色调只留极淡一层(雨雪偏冷), 天气感靠降水/风沙/环境音/闪电表现
WEATHER_PRESETS = {
    'clear': dict(
        label='晴天', ui=(255, 226, 140, 255), dur=(30.0, 55.0),
        sky=(1.04, 1.02, 1.00),                 # 穹顶颜色倍率
        sky_tint=(0.30, 0.50, 0.92), sky_a=0.00,  # 天空罩不再上色(蓝天白云常驻)
        tint=(1.00, 0.90, 0.70), tint_a=0.00,   # 全屏色调 (tint_a=0 表示不加)
        stars=0.00, sun=1.00, clouds=0.95, cloud_col=(1.00, 1.00, 1.00),
        precip='none', density=0,
        ambient=None, amb_vol=0.00,
        wind=0.12, lightning=0.0,
    ),
    'rain': dict(
        label='下雨', ui=(150, 195, 255, 255), dur=(28.0, 48.0),
        sky=(1.00, 1.02, 1.05),                 # 下雨也是蓝天
        sky_tint=(0.30, 0.50, 0.92), sky_a=0.00,
        tint=(0.55, 0.72, 1.00), tint_a=0.10,   # 只留一层很淡的冷色
        stars=0.00, sun=0.55, clouds=1.00, cloud_col=(1.00, 1.00, 1.00),
        precip='rain', density=200,
        ambient='rain', amb_vol=0.60,
        wind=0.45, lightning=1.0,
    ),
    'snow': dict(
        label='下雪', ui=(226, 240, 255, 255), dur=(28.0, 48.0),
        sky=(1.00, 1.03, 1.06),                 # 下雪也是蓝天
        sky_tint=(0.30, 0.50, 0.92), sky_a=0.00,
        tint=(0.72, 0.86, 1.00), tint_a=0.07,
        stars=0.00, sun=0.70, clouds=0.98, cloud_col=(1.00, 1.00, 1.00),
        precip='snow', density=210,
        ambient='snow', amb_vol=0.44,
        wind=0.30, lightning=0.0,
    ),
    'wind': dict(
        label='刮风', ui=(196, 236, 180, 255), dur=(24.0, 42.0),
        sky=(1.03, 1.03, 1.02),                 # 刮风也是蓝天
        sky_tint=(0.30, 0.50, 0.92), sky_a=0.00,
        tint=(1.00, 0.98, 0.92), tint_a=0.05,
        stars=0.00, sun=0.90, clouds=0.92, cloud_col=(1.00, 1.00, 1.00),
        precip='wind', density=200,
        ambient='wind', amb_vol=0.62,
        wind=1.00, lightning=0.0,
    ),
}


def weather_label():
    """HUD 用的 (名称, 颜色)"""
    if WX is None:
        return '—', (200, 200, 215, 255)
    p = WEATHER_PRESETS[WX.kind]
    return p['label'], p['ui']


class RainSheet:
    """相机空间下滚雨幕: 两层平铺雨丝贴图整体往下移, 移满一个贴图格就瞬移回去。

    平移整整一格时画面完全一样(贴图 repeat), 所以肉眼看不出接缝;
    世界空间的雨滴负责近处细节与落地涟漪, 这一层负责铺满视野的雨量。
    """

    # (z, 宽, 高, 平铺x, 平铺y, 格长, alpha, 下滚速度)
    # 第三人称: 雨幕放到角色身后(z=6.5/11), 保证角色永远清晰不被雨纱糊住
    LAYERS = ((6.5, 15.0, 22.5, 5.0, 7.5, 3.0, 0.30, 22.5),
              (11.0, 21.2, 27.5, 7.05, 9.17, 3.0, 0.17, 9.5))

    def __init__(self):
        self.items = []
        for (z, sx, sy, tx, ty, tile, alpha, spd) in self.LAYERS:
            e = Entity(parent=camera, model='quad', scale=(sx, sy, 1), position=(0, 0, z),
                       texture=RAIN_TEX, color=Color(0.78, 0.87, 1.0, alpha),
                       transparency=True, double_sided=True)
            e.texture_scale = (tx, ty)
            e.setDepthWrite(False)              # 别挡住后面的透明物件
            e.enabled = False
            self.items.append({'e': e, 'z': z, 'oy': random.uniform(0, tile), 'ox': 0.0,
                               'tile': tile, 'spd': spd, 'alpha': alpha})

    def update(self, dt, amount, wind_x):
        on = amount > 0.02
        for it in self.items:
            e = it['e']
            if e.enabled != on:
                e.enabled = on
            if not on:
                continue
            t = it['tile']
            k = dt * (0.5 + 0.7 * amount)
            it['oy'] += k * it['spd']
            it['ox'] += k * 1.1 * wind_x * it['spd'] * 0.25
            if it['oy'] >= t:
                it['oy'] -= t
            while it['ox'] >= t:
                it['ox'] -= t
            while it['ox'] <= -t:
                it['ox'] += t
            e.setPos(it['ox'], -it['oy'], it['z'])
            a = it['alpha'] * amount
            if abs(e.color[3] - a) > 0.01:
                e.color = Color(0.78, 0.87, 1.0, a)


class Precip:
    """降水 / 飞沙粒子池: 雨丝(竖长条) · 雪花(圆点) · 风沙(横长条)

    一个池子服务所有天气, 粒子记住自己的 kind, 所以换天气时旧的还会继续落完,
    雨转雪之类会有一段两种同框的过渡。落地时偶尔荡起一圈涟漪。
    """

    CFG = {
        'rain': dict(tex='streak', col=(0.72, 0.83, 1.00, 0.72), size=(0.060, 0.62),
                     fall=(24.0, 31.0), radius=10.0, top=(0.5, 12.0),
                     drift=0.40, splash=0.16),
        'snow': dict(tex='dot', col=(1.00, 1.00, 1.00, 0.95), size=(0.12, 0.24),
                     fall=(1.4, 2.7), radius=12.0, top=(-1.5, 12.0),
                     drift=0.85, splash=0.0),
        'wind': dict(tex='wisp', col=(0.95, 0.91, 0.80, 0.68), size=(0.60, 0.07),
                     fall=(0.2, 0.9), radius=13.0, top=(0.5, 9.0),
                     drift=0.0, splash=0.0),
        'dust': dict(tex='dot', col=(0.96, 0.93, 0.86, 0.50), size=(0.06, 0.13),
                     fall=(0.3, 1.2), radius=12.0, top=(0.0, 8.0),
                     drift=0.0, splash=0.0),
    }

    def __init__(self, n=260, ripples=18):
        self.items = []
        for _ in range(n):
            e = Entity(model='quad', billboard=True, texture=PART_TEX, color=color.white,
                       scale=0.1, transparency=True)
            e.enabled = False
            self.items.append({'e': e, 'vx': 0.0, 'vy': 0.0, 'vz': 0.0, 'life': 0.0,
                               'ph': 0.0, 'kind': '', 'tex': None})
        self.ripples = []
        for _ in range(ripples):
            e = Entity(model='quad', texture=PART_TEX, color=col((0.72, 0.86, 1.00)),
                       rotation_x=90, scale=0.2, transparency=True, double_sided=True)
            e.enabled = False
            self.ripples.append({'e': e, 'life': 0.0, 'max': 0.5, 'size': 0.3})
        self.live = 0

    def _spawn(self, it, kind, cam, wind_dir, wind_str, ground_y, fwd):
        cfg = self.CFG[kind]
        e = it['e']
        R = cfg['radius']
        y = cam.y + random.uniform(cfg['top'][0], cfg['top'][1])
        if kind == 'snow':
            # 雪花飘得慢, 均匀撒在四周(含视野带内), 一生成就看得见
            x = cam.x + random.uniform(-R, R)
            z = cam.z + random.uniform(-R, R)
        else:
            # 雨丝/风丝活得短, 朝视野前方偏置撒, 看上去才够密
            d = random.uniform(3.5, R + 2.0)
            side = random.uniform(-R * 0.85, R * 0.85)
            fx, fz = fwd
            x = cam.x + fx * d + fz * side
            z = cam.z + fz * d - fx * side
        wdx, wdz = wind_dir
        if kind == 'rain':
            vy = random.uniform(*cfg['fall'])
            vx = wdx * wind_str * 5.5 + random.uniform(-0.5, 0.5)
            vz = wdz * wind_str * 5.5 + random.uniform(-0.5, 0.5)
            life = (y - ground_y) / max(vy, 1.0) + 0.1
            sw, sh = cfg['size'][0], cfg['size'][1] * random.uniform(0.70, 1.35)
        elif kind == 'snow':
            vy = random.uniform(*cfg['fall'])
            vx = vz = 0.0
            life = min(16.0, (y - ground_y) / max(vy, 0.4) + 0.4)
            sw = sh = random.uniform(*cfg['size'])
        elif kind == 'wind':                         # 风丝: 贴着风向往远处吹
            sp = (8.0 + 11.0 * wind_str) * random.uniform(0.70, 1.25)
            vx, vz = wdx * sp, wdz * sp
            vy = random.uniform(*cfg['fall'])
            life = random.uniform(1.1, 2.1)
            sw, sh = random.uniform(0.60, 1.40), cfg['size'][1]
        else:                                        # dust: 被风卷着跑的小尘点
            sp = (6.0 + 9.0 * wind_str) * random.uniform(0.60, 1.30)
            vx, vz = wdx * sp, wdz * sp
            vy = random.uniform(*cfg['fall'])
            life = random.uniform(1.0, 2.0)
            sw = sh = random.uniform(*cfg['size'])
        if it['kind'] != kind:
            it['kind'] = kind
            tex = {'streak': STREAK_TEX, 'dot': PART_TEX, 'wisp': WISP_TEX}[cfg['tex']]
            if it['tex'] is not tex:
                e.texture = tex
                it['tex'] = tex
            e.color = Color(*cfg['col'])
        e.setPos(x, y, z)
        e.scale = (sw, sh, 1)
        e.enabled = True
        it['vx'], it['vy'], it['vz'] = vx, vy, vz
        it['life'] = life
        it['ph'] = random.uniform(0, math.tau)

    def _ripple(self, x, y, z):
        for r in self.ripples:
            if r['life'] <= 0:
                r['life'] = r['max'] = random.uniform(0.30, 0.50)
                r['size'] = random.uniform(0.28, 0.55)
                e = r['e']
                e.setPos(x, y, z)
                e.scale = (r['size'] * 0.35, r['size'] * 0.35, 1)
                e.color = Color(0.72, 0.86, 1.00, 0.55)
                e.enabled = True
                return

    def _update_ripples(self, dt):
        for r in self.ripples:
            if r['life'] <= 0:
                continue
            r['life'] -= dt
            e = r['e']
            if r['life'] <= 0:
                e.enabled = False
                continue
            f = 1.0 - r['life'] / r['max']
            s = r['size'] * (0.35 + 1.75 * f)
            e.scale = (s, s, 1)
            e.alpha = 0.55 * (1.0 - f)

    def clear(self):
        for it in self.items:
            if it['life'] > 0:
                it['life'] = 0.0
                it['e'].enabled = False
        for r in self.ripples:
            r['life'] = 0.0
            r['e'].enabled = False

    def update(self, dt, spawns, cam, wind_dir, wind_str, vis, ground_y, ripple_y, t, fwd):
        if vis <= 0.12:                     # 到地下了: 清空, 别让雨落进洞里
            self.clear()
            return
        need = {}
        for kind, cnt in spawns:
            cfg = self.CFG.get(kind)
            if cfg is not None and cnt > 0:
                need[kind] = need.get(kind, 0) + int(cnt * vis)
        wdx, wdz = wind_dir
        live = 0
        for it in self.items:
            e = it['e']
            if it['life'] <= 0.0:
                for nk in need:
                    if need[nk] > 0:
                        need[nk] -= 1
                        self._spawn(it, nk, cam, wind_dir, wind_str, ground_y, fwd)
                        live += 1
                        break
                continue
            live += 1
            k = it['kind']
            it['life'] -= dt * (4.0 if not need.get(k) else 1.0)   # 该天气已结束: 加速消散
            cfg = self.CFG[k]
            x, y, z = e.getX(), e.getY(), e.getZ()
            if k == 'snow':                 # 雪花: 慢慢飘 + 左右摇摆
                x += (math.sin(t * 1.7 + it['ph']) * cfg['drift'] + wdx * wind_str * 2.4) * dt
                z += (math.cos(t * 1.31 + it['ph'] * 1.7) * cfg['drift'] + wdz * wind_str * 2.4) * dt
            elif k in ('wind', 'dust'):     # 风丝/飞尘: 跟着阵风跑
                x += (it['vx'] + wdx * wind_str * 4.0) * dt
                z += (it['vz'] + wdz * wind_str * 4.0) * dt
                if abs(x - cam.x) > 26 or abs(z - cam.z) > 26:
                    it['life'] = 0.0
            else:                           # 雨: 直下 + 被风吹斜
                x += it['vx'] * dt
                z += it['vz'] * dt
            y -= it['vy'] * dt
            if it['life'] <= 0.0 or y <= ground_y:
                it['life'] = 0.0
                e.enabled = False
                if k == 'rain' and random.random() < cfg['splash']:
                    self._ripple(x, ripple_y, z)
                continue
            e.setPos(x, y, z)
            if k in ('wind', 'dust'):
                e.alpha = cfg['col'][3] * min(1.0, it['life'] / 0.35)
        self.live = live
        self._update_ripples(dt)


class WeatherSystem:
    """随机天气调度 + 所有天气表现(天空/云/太阳/星星/降水/闪电/风/环境音)

    * 每 24~55 秒随机换一种天气, 用 smoothstep 在 TRANS 秒内交叉过渡;
    * 表现全部走"顶点色烘焙"路线: 穹顶颜色倍率 + 全屏色调层, 不用灯光和 shader;
    * 玩家下潜到地下时 vis -> 0, 降水清空、环境音变闷、色调撤掉。
    """

    TRANS = 2.8

    def __init__(self, n=260):
        forced = os.environ.get('RW_WEATHER', '').strip().lower()
        self.locked = forced if forced in WEATHER_ORDER else None
        self.kind = self.locked or 'clear'      # 开局蓝天白云, 之后随机变化
        self.prev = self.kind
        self._first = True
        self.blend = 1.0
        self.clock = 0.0
        self.timer = random.uniform(*WEATHER_PRESETS[self.kind]['dur'])
        self.wind_dir = self._rand_dir()
        self.wind_goal = self.wind_dir
        self.wind_str = WEATHER_PRESETS[self.kind]['wind']
        self.gust = random.uniform(0, 50)
        self.flash = 0.0
        self.bolt_t = random.uniform(5.0, 14.0)
        self.vis = 1.0
        self.precip = Precip(n)
        self._stars_a = -1.0
        self._cloud_a = -1.0
        self._cloud_c = None
        # 全屏色调层: 挂在相机前面(3D pass), 所以永远在 HUD 之下
        self.tint = Entity(parent=camera, model='quad', scale=14.0, position=(0, 0, 0.42),
                           color=Color(0, 0, 0, 0), transparency=True)
        self.tint.setDepthWrite(False)
        self.tint.enabled = False
        self.sheet = RainSheet()

    # -- 工具 --
    @staticmethod
    def _rand_dir():
        a = random.uniform(0, math.tau)
        return (math.cos(a), math.sin(a))

    def _b(self, key):
        """prev -> kind 的插值 (smoothstep)"""
        f = self.blend * self.blend * (3 - 2 * self.blend)
        a = WEATHER_PRESETS[self.prev][key]
        b = WEATHER_PRESETS[self.kind][key]
        if isinstance(a, tuple):
            return tuple(a[i] + (b[i] - a[i]) * f for i in range(len(a)))
        return a + (b - a) * f

    @property
    def label(self):
        return WEATHER_PRESETS[self.kind]['label']

    def set_weather(self, kind, instant=False, announce=True):
        if kind not in WEATHER_PRESETS or kind == self.kind:
            return
        self.prev, self.kind = self.kind, kind
        self.blend = 1.0 if instant else 0.0
        self.timer = random.uniform(*WEATHER_PRESETS[kind]['dur'])
        self.wind_goal = self._rand_dir()
        if WEATHER_PRESETS[kind]['lightning'] > 0:
            self.bolt_t = random.uniform(3.0, 9.0)
        if announce and HUDI is not None and G.state not in ('title',):
            HUDI.show_toast('天气变化 · %s' % WEATHER_PRESETS[kind]['label'])
            if SFX is not None:
                SFX.play('ui', volume=0.45)
        G.hud_dirty = True

    def cycle(self):
        i = WEATHER_ORDER.index(self.kind)
        self.set_weather(WEATHER_ORDER[(i + 1) % len(WEATHER_ORDER)])

    def reroll(self):
        """重开一局: 换一种天气, 不做过渡也不提示; 首次开局固定晴天(蓝天白云)"""
        if self._first:
            self._first = False
            kind = self.locked or 'clear'
        else:
            kind = self.locked or random.choice(WEATHER_ORDER)
        if kind == self.kind:
            return
        self.prev = self.kind = kind
        self.blend = 1.0
        self.timer = random.uniform(*WEATHER_PRESETS[kind]['dur'])
        self.wind_goal = self._rand_dir()
        self.bolt_t = random.uniform(5.0, 14.0)

    # -- 主循环 --
    def update(self, dt):
        self.clock += dt
        p = G.player
        if p is None or p.mode == 'surface':
            tv = 1.0
        elif p.mode == 'cave':
            tv = 0.0
        elif p.mode == 'dive':
            tv = 1.0 - min(1.0, p.trans_t / 0.9)
        else:                                   # rise
            tv = min(1.0, p.trans_t / 0.9)
        self.vis += (tv - self.vis) * min(1.0, 9.0 * dt)

        if G.state == 'play' and self.locked is None:
            self.timer -= dt
            if self.timer <= 0:
                self.set_weather(random.choice([k for k in WEATHER_ORDER if k != self.kind]))
        if self.blend < 1.0:
            self.blend = min(1.0, self.blend + dt / self.TRANS)

        # 风力(带阵风) + 风向缓慢游走
        wt = self._b('wind')
        self.gust += dt * (0.7 + wt * 1.9)
        g = 0.70 + 0.30 * math.sin(self.gust * 1.13) * math.sin(self.gust * 0.47 + 1.7)
        self.wind_str += (wt * g - self.wind_str) * min(1.0, 2.5 * dt)
        dx, dz = self.wind_dir
        gx, gz = self.wind_goal
        kk = min(1.0, 0.6 * dt)
        nx, nz = dx + (gx - dx) * kk, dz + (gz - dz) * kk
        L = math.hypot(nx, nz) or 1.0
        self.wind_dir = (nx / L, nz / L)
        if random.random() < dt * 0.06:
            self.wind_goal = self._rand_dir()

        # 闪电
        if (WEATHER_PRESETS[self.kind]['lightning'] > 0 and self.blend > 0.55
                and self.vis > 0.4 and G.state == 'play'):
            self.bolt_t -= dt
            if self.bolt_t <= 0:
                self.bolt_t = random.uniform(7.0, 20.0)
                self.flash = 1.0
                if SFX is not None:
                    SFX.play('thunder', volume=random.uniform(0.40, 0.75))
        if self.flash > 0:
            self.flash = max(0.0, self.flash - dt * 2.4)

        self._apply(dt)
        self._precip(dt)
        self._sheet(dt)
        self._ambient()

    def _apply(self, dt):
        vis = self.vis
        sky = self._b('sky')
        WORLD['dome'].color = Color(max(0, sky[0]), max(0, sky[1]), max(0, sky[2]), 1.0)
        stc = self._b('sky_tint')
        sta = self._b('sky_a') * max(0.15, vis)
        if sta > 0.01:
            WORLD['sky_tint'].enabled = True
            WORLD['sky_tint'].color = Color(stc[0], stc[1], stc[2], sta)
        else:
            WORLD['sky_tint'].enabled = False

        sa = self._b('stars') * vis
        if abs(sa - self._stars_a) > 0.02:
            self._stars_a = sa
            for st in WORLD['stars']:
                st.alpha = st.base_alpha * sa

        su = self._b('sun') * vis
        WORLD['sun'].alpha = 0.95 * su
        WORLD['sun_halo'].alpha = 0.28 * su
        on = su > 0.02
        WORLD['sun'].enabled = on
        WORLD['sun_halo'].enabled = on

        ca = self._b('clouds') * vis
        cc = self._b('cloud_col')
        wdx, wdz = self.wind_dir
        for c in WORLD['clouds']:
            sp = c.spd * (0.35 + self.wind_str * 3.2)
            c.x += wdx * sp * dt
            c.z += wdz * sp * dt
            if c.x > 64:
                c.x = -64
            elif c.x < -64:
                c.x = 64
            if c.z > 64:
                c.z = -64
            elif c.z < -64:
                c.z = 64
        cc_changed = (self._cloud_c is None
                      or max(abs(cc[i] - self._cloud_c[i]) for i in range(3)) > 0.02)
        if cc_changed or abs(ca - self._cloud_a) > 0.015:
            self._cloud_a, self._cloud_c = ca, cc
            ccol = Color(cc[0], cc[1], cc[2], 1.0)
            for c in WORLD['clouds']:
                c.color = ccol
                a = ca * c.var
                c.alpha = a
                c.enabled = a > 0.02

        tc = self._b('tint')
        ta = self._b('tint_a') * vis
        if self.flash > 0.001:
            fl = self.flash * self.flash * (0.62 + 0.38 * math.sin(self.flash * 47.0))
            fl = max(0.0, fl)
            ta = min(0.95, ta + fl * 0.90 * vis)
            tc = (tc[0] + (1 - tc[0]) * fl, tc[1] + (1 - tc[1]) * fl, tc[2] + (1 - tc[2]) * fl)
        if ta > 0.004:
            self.tint.enabled = True
            self.tint.color = Color(max(0, tc[0]), max(0, tc[1]), max(0, tc[2]), ta)
        elif self.tint.enabled:
            self.tint.enabled = False

    def _sheet(self, dt):
        f = self.blend * self.blend * (3 - 2 * self.blend)
        amt = 0.0
        if self.prev == 'rain':
            amt += 1 - f
        if self.kind == 'rain':
            amt += f
        self.sheet.update(dt, amt * self.vis, self.wind_dir[0])

    @staticmethod
    def _split(kind, density):
        """刮风 = 风丝 + 飞尘 两层"""
        if kind == 'wind':
            return [('wind', density * 0.62), ('dust', density * 0.60)]
        return [(kind, density)]

    def _precip(self, dt):
        f = self.blend * self.blend * (3 - 2 * self.blend)
        pre, cur = WEATHER_PRESETS[self.prev], WEATHER_PRESETS[self.kind]
        if self.blend >= 1.0:
            spawns = self._split(cur['precip'], cur['density'])
        else:                                   # 过渡期两种同框
            spawns = (self._split(pre['precip'], pre['density'] * (1 - f))
                      + self._split(cur['precip'], cur['density'] * f))
        yaw = G.cam_yaw
        fwd = (math.sin(yaw), math.cos(yaw))
        self.precip.update(dt, spawns, camera, self.wind_dir, self.wind_str, self.vis,
                           SURF_Y - 0.05, SURF_Y + 0.06, self.clock, fwd)

    def _ambient(self):
        if SFX is None:
            return
        f = self.blend * self.blend * (3 - 2 * self.blend)
        pre, cur = WEATHER_PRESETS[self.prev], WEATHER_PRESETS[self.kind]
        muffle = 0.20 + 0.80 * self.vis          # 地下听着闷
        for name in ('rain', 'wind', 'snow'):
            v = 0.0
            if pre['ambient'] == name:
                v += pre['amb_vol'] * (1 - f)
            if cur['ambient'] == name:
                v += cur['amb_vol'] * f
            SFX.set_ambient(name, v * muffle)


# ----------------------------------------------------------------------------
# 妖怪
# ----------------------------------------------------------------------------
class Monster(Entity):
    def __init__(self, pos, kind=0):
        super().__init__(position=pos)
        self.kind = kind
        base = GREEN if kind == 0 else RED
        self.base_color = base
        self.hp = 3
        self.speed = 1.05 if kind == 0 else 1.45   # 移动更缓慢, 方便瞄准
        self.state = 'wander'
        self.target = Vec3(pos)
        self.timer = random.uniform(1.5, 4)
        self.phase = random.uniform(0, 6)
        self.flash = 0.0
        self.dead = False
        self.die_t = 0.0
        self.move_dir = Vec3(0, 0, 1)

        self.body = Entity(parent=self, model='rw_sphere', color=col(base), scale=(0.95, 0.85, 0.9), y=0.85)
        Entity(parent=self.body, model='rw_sphere_lo', color=tinted(base, 0.22), scale=(0.62, 0.5, 0.4), y=-0.18, z=-0.42)
        for sx in (-0.28, 0.28):
            h = Entity(parent=self.body, model='rw_cone', color=col((0.95, 0.9, 0.8)), scale=(0.22, 0.5, 0.22),
                       position=(sx, 0.72, 0))
            h.rotation_z = -18 if sx < 0 else 18
            eye = Entity(parent=self.body, model='rw_sphere_lo', color=color.white, scale=0.36,
                         position=(sx * 0.85, 0.22, -0.38))
            Entity(parent=eye, model='rw_sphere_lo', color=color.black, scale=0.42, z=-0.55)
        Entity(parent=self.body, model='quad', color=col((0.25, 0.05, 0.1)), scale=(0.34, 0.16, 1),
               position=(0, -0.22, -0.86), double_sided=True)
        self.body.rotation_y = 180        # 脸(眼睛/嘴)朝向移动方向
        for sx in (-0.3, 0.3):
            Entity(parent=self, model='rw_sphere_lo', color=tinted(base, -0.18), scale=0.34,
                   position=(sx, 0.16, 0))

    def hit(self, knock):
        if self.dead:
            return
        self.hp -= 1
        self.flash = 0.18
        self.position += Vec3(knock[0], 0, knock[2]) * 0.5
        FX.burst(self.world_position + Vec3(0, 1, 0), (1, 1, 0.8), 8, 5, 0.4, 0.2)
        SFX.play('hit')
        if self.hp <= 0:
            self.dead = True
            SFX.play('die')
            FX.burst(self.world_position + Vec3(0, 1, 0), self.base_color, 22, 6, 0.8, 0.3, g=6)
            G.kills += 1
            G.hud_dirty = True

    def update(self, dt=None):
        dt = time.dt if dt is None else dt
        if self.dead:
            self.die_t += dt
            s = max(0.01, 1 - self.die_t * 2.2)
            self.scale = s
            self.rotation_y += 420 * dt
            self.y += dt * 1.5
            if self.die_t > 0.5:
                if self in G.monsters:
                    G.monsters.remove(self)
                destroy(self)
            return
        if self.flash > 0:
            self.flash -= dt
            self.body.color = color.white if int(self.flash * 30) % 2 == 0 else col(self.base_color)
        # --- 纯随机游荡: 不追踪玩家, 也不会伤害玩家 ---
        self.timer -= dt
        if self.timer <= 0:
            self.timer = random.uniform(1.4, 4.2)
            roll = random.random()
            if roll < 0.20:
                self.state = 'idle'                       # 原地蹦跶歇一会
            else:
                self.state = 'wander'
                if roll < 0.55:                           # 随机换个朝向继续走
                    a = random.uniform(0, math.tau)
                    self.move_dir = Vec3(math.cos(a), 0, math.sin(a))
                else:                                     # 随机挑场地里一个点走过去
                    a = random.uniform(0, math.tau)
                    r = random.uniform(2, SURF_HALF - 1)
                    to = Vec3(math.cos(a) * r, 0, math.sin(a) * r) - self.position
                    to.y = 0
                    if to.length() > 0.4:
                        self.move_dir = to.normalized()
        p = G.player
        away = self.position - p.position
        hd = math.hypot(away.x, away.z)
        if hd < 2.4 and p.mode in ('surface', 'cave'):   # 别贴着玩家的脸, 稍微让开
            av = Vec3(away.x, 0, away.z)
            if av.length() > 1e-4:
                self.move_dir = (self.move_dir + av.normalized() * 1.6).normalized()
            self.state = 'wander'
        if self.state == 'wander':
            self.position += self.move_dir * self.speed * dt
            self.rotation_y = lerp(self.rotation_y,
                                   math.degrees(math.atan2(self.move_dir.x, self.move_dir.z)), 6 * dt)
        mp = self.position
        lim = SURF_HALF - 0.5
        if mp.x < -lim or mp.x > lim:                     # 撞到场边就反弹
            mp.x = clamp(mp.x, -lim, lim)
            self.move_dir = Vec3(-self.move_dir.x, 0, self.move_dir.z)
        if mp.z < -lim or mp.z > lim:
            mp.z = clamp(mp.z, -lim, lim)
            self.move_dir = Vec3(self.move_dir.x, 0, -self.move_dir.z)
        self.position = mp
        self.phase += dt * (2.3 if self.state == 'wander' else 1.2)
        self.y = SURF_Y + abs(math.sin(self.phase)) * 0.22
        self.body.scale_y = 0.85 * (1 + 0.08 * math.sin(self.phase * 2))


# ----------------------------------------------------------------------------
# 宝藏 / 拾取物 / 可破坏物
# ----------------------------------------------------------------------------
class Treasure(Entity):
    def __init__(self, pos, beam=True, glow=GOLD):
        super().__init__(position=pos)
        self.glow = glow
        self.t = random.uniform(0, 6)
        self.gem = Entity(parent=self, model='rw_gem', color=col(glow), scale=0.85)
        Entity(parent=self, model='rw_ring', color=col(glow), scale=1.0, y=-0.75)
        if beam:
            b = Entity(parent=self, model='rw_tube', color=col(CYAN), scale=(0.55, 9, 0.55),
                       y=4.0, double_sided=True, transparency=True)
            b.alpha = 0.16
        self.spark_t = 0.0

    def update(self, dt=None):
        dt = time.dt if dt is None else dt
        self.t += dt
        self.gem.rotation_y += 120 * dt
        self.y = self.start_y + math.sin(self.t * 2) * 0.18
        self.spark_t -= dt
        if self.spark_t <= 0:
            self.spark_t = random.uniform(0.9, 1.8)
            FX.burst(self.world_position, self.glow, 1, 1.0, 0.6, 0.10, g=1.0, up=1.2)

    @property
    def start_y(self):
        if not hasattr(self, '_sy'):
            self._sy = self.y
        return self._sy


class Breakable(Entity):
    def __init__(self, pos, kind='crystal', content=None):
        super().__init__(position=pos)
        self.kind = kind
        self.content = content      # 'treasure' | None
        self.hp = 2
        self.flash = 0.0
        if kind == 'crystal':
            self.ball = Entity(parent=self, model='rw_sphere', color=col(CYAN), scale=1.15,
                               transparency=True, y=0.55)
            self.ball.alpha = 0.55
            self.inner = Entity(parent=self, model='rw_gem', color=col(GOLD), scale=0.6, y=0.55)
        else:
            self.ball = Entity(parent=self, model='rw_ball', color=col(BROWN), scale=1.15, y=0.5)
            self.inner = None
        G.breakables.append(self)

    def hit(self):
        self.hp -= 1
        self.flash = 0.15
        SFX.play('break')
        FX.burst(self.world_position + Vec3(0, 0.6, 0),
                 CYAN if self.kind == 'crystal' else BROWN, 10, 5, 0.5, 0.2)
        if self.hp <= 0:
            if self.content == 'treasure':
                t = Treasure(self.world_position + Vec3(0, 1.0, 0), beam=True)
                G.treasures.append(t)
            FX.burst(self.world_position + Vec3(0, 0.6, 0), (1, 1, 1), 16, 6, 0.6, 0.25)
            if self in G.breakables:
                G.breakables.remove(self)
            destroy(self)

    def update(self, dt=None):
        dt = time.dt if dt is None else dt
        if self.flash > 0:
            self.flash -= dt
            s = 1.15 + math.sin(self.flash * 60) * 0.08
            self.ball.scale = s
        if self.inner:
            self.inner.rotation_y += 60 * dt


# ----------------------------------------------------------------------------
# 主人公 (圆头 + 圆头剑)
# ----------------------------------------------------------------------------
class Player(Entity):
    """第三人称主人公: 镜头在身后环视, 圆头小人手里握着圆头剑"""

    EYE = 1.62            # 保留: 角色眼高(镜头目标高度另见 CAM_TARGET_Y)

    def __init__(self):
        super().__init__(position=(0, SURF_Y, 0))
        self.vy = 0.0
        self.on_ground = True
        self.jumps = 0
        self.mode = 'surface'      # surface | dive | cave | rise
        self.trans_t = 0.0
        self.swing_t = -1.0
        self.walk_t = 0.0
        self.moving = 0.0
        self.body_yaw = 0.0
        self._hit_flag = False
        self._snapped = False      # 穿梭过半时镜头瞬移一次

        # ---- 可见角色模型 (局部 +Z 为正面, -Z 为背面) ----
        # 设计要点: 背面=帽子+后脑+背包, 绝不出现"像脸"的缝; 正面=凸出的眼睛+嘴
        self.model = Entity(parent=self)
        m = self.model
        self.leg_l = Entity(parent=m, position=(-0.17, 0.66, 0))
        self.leg_r = Entity(parent=m, position=(0.17, 0.66, 0))
        for leg in (self.leg_l, self.leg_r):
            Entity(parent=leg, model='rw_box', color=col((0.30, 0.24, 0.52)),
                   scale=(0.19, 0.66, 0.21), y=-0.33)
            Entity(parent=leg, model='rw_sphere_lo', color=col(BROWN), scale=0.24,
                   position=(0, -0.64, 0.06))
        # 躯干 (顶边低于下巴, 避免从背后看像"嘴")
        Entity(parent=m, model='rw_box', color=col(TUNIC), scale=(0.60, 0.56, 0.38), y=0.94,
               double_sided=True)
        Entity(parent=m, model='rw_box', color=col(GOLD), scale=(0.62, 0.10, 0.40), y=0.72)
        Entity(parent=m, model='rw_sphere_lo', color=col(SKIN), scale=0.22, y=1.24,
               double_sided=True)                                                   # 脖子
        Entity(parent=m, model='rw_sphere', color=col(SKIN), scale=0.62, y=1.56,
               double_sided=True)                                                   # 圆头
        # 帽子: 帽檐贴在头顶高处(double_sided 避免背面透洞), 帽尖向上
        Entity(parent=m, model='rw_sphere_lo', color=col((0.92, 0.72, 0.30)),
               scale=(0.74, 0.14, 0.74), y=1.84, double_sided=True)
        Entity(parent=m, model='rw_cone', color=col((0.92, 0.72, 0.30)),
               scale=(0.42, 0.52, 0.42), y=2.08)
        # 脸 (只在 +Z 面): 凸出的圆眼 + 嘴
        for sx in (-0.15, 0.15):
            eye = Entity(parent=m, model='rw_sphere_lo', color=color.white, scale=0.16,
                         position=(sx, 1.60, 0.26))
            Entity(parent=eye, model='rw_sphere_lo', color=color.black, scale=0.5, z=0.62)
        Entity(parent=m, model='quad', color=col((0.55, 0.16, 0.22)), scale=(0.16, 0.08, 1),
               position=(0, 1.44, 0.30), double_sided=True)
        # 背包 (只在 -Z 面): 背后的强烈方位线索
        Entity(parent=m, model='rw_box', color=col(BROWN), scale=(0.40, 0.44, 0.20),
               position=(0, 1.02, -0.28), double_sided=True)
        Entity(parent=m, model='rw_box', color=col((0.32, 0.20, 0.12)), scale=(0.42, 0.14, 0.22),
               position=(0, 1.20, -0.28), double_sided=True)
        Entity(parent=m, model='rw_box', color=col((0.55, 0.35, 0.62)), scale=(0.46, 0.14, 0.16),
               position=(0, 0.80, -0.30), double_sided=True)
        self.arm_l = Entity(parent=m, position=(-0.40, 1.20, 0))
        self.arm_r = Entity(parent=m, position=(0.40, 1.20, 0))
        for arm in (self.arm_l, self.arm_r):
            Entity(parent=arm, model='rw_box', color=col((0.16, 0.44, 0.70)),
                   scale=(0.15, 0.50, 0.17), y=-0.25)
            Entity(parent=arm, model='rw_sphere_lo', color=col(SKIN), scale=0.17, y=-0.52)
        # ---- 圆头剑 (握在右手, 剑尖是发光圆球) ----
        self.hand = Entity(parent=self.arm_r, position=(0, -0.52, 0.06))
        Entity(parent=self.hand, model='rw_box', color=col(BROWN), scale=(0.07, 0.26, 0.07), y=0.02)
        Entity(parent=self.hand, model='rw_box', color=col(GOLD), scale=(0.32, 0.08, 0.10), y=0.16)
        Entity(parent=self.hand, model='rw_box', color=col(STEEL), scale=(0.09, 0.92, 0.05), y=0.66)
        self.sword_tip = Entity(parent=self.hand, model='rw_sphere_lo', color=col(CYAN),
                                scale=0.24, y=1.16)
        Entity(parent=self.sword_tip, model='rw_sphere_lo', color=color.white, scale=0.5,
               transparency=True, alpha=0.35)
        self.hand.rotation_x = -18          # 平时斜扛在肩侧
        self.hand.rotation_z = -12
        # ---- 挥剑刀光 (挂在角色身上, 随身体一起转) ----
        self.slash = Entity(parent=m, model='rw_slash', color=col((0.8, 0.95, 1.0)),
                            position=(0.30, 1.15, 0.85), scale=1.5,
                            transparency=True, double_sided=True)
        self.slash.enabled = False

    # -- 攻击 --
    def attack(self):
        if self.swing_t >= 0 or G.state != 'play':
            return
        self.swing_t = 0.0
        SFX.play('swing')
        self.slash.enabled = True
        self.slash.alpha = 0.9

    # 攻击判定参数: 刻意放宽, 挥剑更容易命中
    HIT_RANGE = 5.2          # 最远命中距离
    HIT_CLOSE = 2.8          # 贴身范围内无视朝向必中
    HIT_Y_TOL = 3.6          # 高度容忍
    HIT_DOT = -0.10          # 朝向点积阈值: 约 190 度扇形, 几乎"面朝就算"

    def do_hit_check(self):
        fwd = Vec3(math.sin(G.cam_yaw), 0, math.cos(G.cam_yaw))
        for m in list(G.monsters):
            if m.dead:
                continue
            d = m.position - self.position
            if abs(d.y) > self.HIT_Y_TOL:
                continue
            hd = math.hypot(d.x, d.z)
            if hd > self.HIT_RANGE:
                continue
            if hd <= self.HIT_CLOSE or \
                    (fwd.x * d.x + fwd.z * d.z) / max(hd, 1e-5) > self.HIT_DOT:
                m.hit(fwd)
        for b in list(G.breakables):
            d = b.position - self.position
            if abs(d.y) < 3.6 and math.hypot(d.x, d.z) < 4.2:
                b.hit()

    def update(self, dt=None):
        dt = time.dt if dt is None else dt
        if G.state != 'play':
            return

        # --- 穿梭过渡 ---
        if self.mode in ('dive', 'rise'):
            self.trans_t += dt
            f = min(1, self.trans_t / 0.9)
            e = f * f * (3 - 2 * f)
            if self.mode == 'dive':
                self.y = lerp(SURF_Y, CAVE_G, e)
            else:
                self.y = lerp(CAVE_G, SURF_Y, e)
            # 角色缩进地面 / 从地面钻出; 中点全屏淡黑遮住镜头换层
            s = max(0.02, 1 - e) if self.mode == 'dive' else max(0.02, e)
            self.model.scale = s
            G.fade = max(0.0, min(1.0, math.sin(math.pi * f) * 2.4 - 0.55))
            if not self._snapped and f >= 0.5:
                self._snapped = True
                G.cam_snap = True
            if int(self.trans_t * 20) % 3 == 0:
                FX.burst(self.world_position + Vec3(0, 0.8, 0), PURPLE, 1, 2.5, 0.5, 0.18, g=2)
            if f >= 1:
                self.mode = 'cave' if self.mode == 'dive' else 'surface'
                self.vy = 0
                self.on_ground = True
                self.model.scale = 1
                G.fade = 0.0
                self._snapped = False
                G.hud_dirty = True
            self._anim(dt, 0)
            return

        # --- 移动 (第三人称: W 前 / S 后 / A 左 / D 右, 均相对镜头朝向) ---
        fwd = Vec3(math.sin(G.cam_yaw), 0, math.cos(G.cam_yaw))
        right = Vec3(fwd.z, 0, -fwd.x)
        wish = Vec3(0, 0, 0)
        if held_keys['w']:
            wish += fwd
        if held_keys['s']:
            wish -= fwd
        if held_keys['d']:
            wish += right
        if held_keys['a']:
            wish -= right
        speed = 9.0 if held_keys['shift'] else 6.0
        if wish.length() > 0.01:
            wish = wish.normalized()
            self.position += wish * speed * dt
            self.moving = lerp(self.moving, 1, 8 * dt)
        else:
            self.moving = lerp(self.moving, 0, 8 * dt)
        self.body_yaw = lerp_angle(self.body_yaw, G.cam_yaw, min(1.0, 14 * dt))
        self.rotation_y = math.degrees(self.body_yaw)

        # --- 边界 ---
        half = SURF_HALF - 0.4 if self.mode == 'surface' else CAVE_HALF
        pp = self.position
        # 大风会推着人走一点, 腾空时最明显
        if WX is not None and WX.wind_str > 0.05 and WX.vis > 0.5:
            s = WX.wind_str * (0.62 if not self.on_ground else 0.13) * dt
            pp.x += WX.wind_dir[0] * s
            pp.z += WX.wind_dir[1] * s
        pp.x = clamp(pp.x, -half, half)
        pp.z = clamp(pp.z, -half, half)
        self.position = pp

        # --- 重力 / 落地 ---
        prev_y = self.y
        self.vy -= GRAV * dt
        self.y += self.vy * dt
        ground = SURF_Y if self.mode == 'surface' else CAVE_G
        self.on_ground = False
        if self.mode == 'surface':
            # 浮空平台
            for (px, pz, top, ph) in PLATFORMS:
                if abs(self.x - px) < ph and abs(self.z - pz) < ph and self.vy <= 0:
                    if prev_y >= top - 0.05 and self.y <= top:
                        self.y = top
                        self.vy = 0
                        self.on_ground = True
                        self.jumps = 0
            # 弹跳球
            bx, bz = BOUNCE_POS
            if self.vy <= 0 and math.hypot(self.x - bx, self.z - bz) < 1.3 and prev_y >= 1.0 and self.y <= 1.5:
                self.y = 1.5
                self.vy = 25.0
                self.jumps = 1
                SFX.play('bounce')
                FX.burst(Vec3(bx, 1.4, bz), (1.0, 0.5, 0.8), 16, 6, 0.6, 0.3)
                G.bounce_squash = 0.3
        if self.y <= ground:
            self.y = ground
            self.vy = 0
            self.on_ground = True
            self.jumps = 0
        if self.mode == 'cave' and self.y > CAVE_CEIL:
            self.y = CAVE_CEIL
            self.vy = min(self.vy, 0)
        self._anim(dt, self.moving)

        # --- 挥剑动画 (第三人称: 右臂抡圆斜劈) ---
        if self.swing_t >= 0:
            self.swing_t += dt
            f = min(1, self.swing_t / 0.34)
            e = f * f * (3 - 2 * f)
            self.arm_r.rotation_x = lerp(-125, 55, e)
            self.arm_r.rotation_z = lerp(-38, 26, e)
            self.arm_r.rotation_y = lerp(24, -34, e)
            self.model.rotation_x = lerp(7, -5, e)      # 身体跟着前倾后仰
            self.slash.rotation_z = lerp(52, -52, e)
            self.slash.alpha = max(0, 0.9 * (1 - f))
            if self.swing_t >= 0.10 and not self._hit_flag:
                self._hit_flag = True
                self.do_hit_check()
            if f >= 1:
                self.swing_t = -1
                self.arm_r.rotation = (0, 0, 0)
                self.model.rotation_x = 0
                self.slash.enabled = False
                self._hit_flag = False
        else:
            self._hit_flag = False

    def _anim(self, dt, move):
        self.walk_t += dt * (2 + move * 9)
        sw = math.sin(self.walk_t) * 36 * move
        self.leg_l.rotation_x = sw
        self.leg_r.rotation_x = -sw
        self.arm_l.rotation_x = -sw * 0.65
        if self.swing_t < 0:                 # 攻击时右臂交给挥剑逻辑
            self.arm_r.rotation_x = sw * 0.65
        if not self.on_ground:               # 腾空收腿
            self.leg_l.rotation_x = lerp(self.leg_l.rotation_x, -26, min(1, 8 * dt))
            self.leg_r.rotation_x = lerp(self.leg_r.rotation_x, 12, min(1, 8 * dt))
        self.model.y = abs(math.sin(self.walk_t)) * 0.03 * move


# ----------------------------------------------------------------------------
# 游戏总控
# ----------------------------------------------------------------------------
class Game:
    def __init__(self):
        self.state = 'title'          # title | play | pause | win | lose
        self.t = 0.0
        self.got = 0
        self.kills = 0
        self.monsters = []
        self.treasures = []
        self.breakables = []
        self.holes = []
        self.cam_yaw = 0.0
        self.cam_pitch = 16.0
        self.hud_dirty = True
        self.bounce_squash = 0.0
        self.spawn_timer = 8.0
        self.fade = 0.0            # 穿梭全屏淡黑强度 0..1
        self.cam_snap = True       # 镜头瞬移标记(重开/穿梭换层时用)
        self.player = None
        self.frame = 0
        self.fps_acc = 0.0
        self.fps_n = 0
        self.fps = 60.0


G = Game()
FX = None
SFX = None


class SoundBank:
    def __init__(self, paths):
        self.paths = paths
        self.pool = {}
        self.music = None
        self.amb = {}

    def play(self, name, volume=1.0):
        if name not in self.pool:
            rel = os.path.relpath(self.paths[name], GAME_DIR).replace(os.sep, '/')
            self.pool[name] = Audio(rel, autoplay=False, volume=volume)
        a = self.pool[name]
        a.volume = volume
        a.play()

    def start_music(self):
        if self.music is None:
            rel = os.path.relpath(self.paths['music'], GAME_DIR).replace(os.sep, '/')
            self.music = Audio(rel, loop=True, autoplay=True, volume=0.5)

    def ambient(self, name):
        """取(或惰性创建)一个循环环境音, 音量常驻可调"""
        a = self.amb.get(name)
        if a is None:
            rel = os.path.relpath(self.paths[name], GAME_DIR).replace(os.sep, '/')
            a = Audio(rel, loop=True, autoplay=True, volume=0.0)
            self.amb[name] = a
        return a

    def set_ambient(self, name, vol):
        if name not in self.paths:
            return
        a = self.ambient(name)
        v = max(0.0, min(1.0, vol))
        if abs(a.volume - v) > 0.004:
            a.volume = v

    def preload_ambients(self, names):
        for n in names:
            if n in self.paths:
                self.ambient(n)


# ----------------------------------------------------------------------------
# 世界搭建
# ----------------------------------------------------------------------------
WORLD = {}


def build_world():
    w = {}
    w['dome'] = Entity(model='rw_dome', position=(0, -6, 0), double_sided=True)
    # 内层天空罩: 半透明球壳, 用来把天空整体染成阴/雨/雪的色相
    w['sky_tint'] = Entity(model='rw_dome', scale=0.965, position=(0, -6, 0),
                           double_sided=True, transparency=True,
                           color=Color(0, 0, 0, 0))
    w['sky_tint'].setDepthWrite(False)
    w['sky_tint'].enabled = False
    w['stars'] = []
    for _ in range(60):
        a = random.uniform(0, math.tau)
        e = random.uniform(0.12, 0.9)
        r = 55.0
        st = Entity(model='quad', billboard=True, texture=PART_TEX, color=color.white,
                    scale=random.uniform(0.5, 1.4),
                    position=(math.cos(a) * r * math.cos(e), 6 + math.sin(e) * r * 0.9,
                              math.sin(a) * r * math.cos(e)))
        st.alpha = random.uniform(0.4, 0.9)
        st.base_alpha = st.alpha
        w['stars'].append(st)
    # 太阳 + 光晕 (晴天露脸, 阴雨雪天被云吃掉)
    sd = LIGHT * 52.0
    w['sun'] = Entity(model='quad', billboard=True, texture=PART_TEX, color=col((1.0, 0.96, 0.84)),
                      scale=9.0, position=(sd.x, sd.y - 6.0, sd.z), transparency=True)
    w['sun_halo'] = Entity(model='quad', billboard=True, texture=PART_TEX, color=col((1.0, 0.88, 0.62)),
                           scale=30.0, position=(sd.x, sd.y - 6.0, sd.z), transparency=True)
    w['sun_halo'].alpha = 0.26
    # 云: 会被风吹着走, 阴天变厚变暗
    w['clouds'] = []
    for _ in range(16):
        a = random.uniform(0, math.tau)
        r = random.uniform(16, 50)
        c = Entity(model='quad', billboard=True, texture=CLOUD_TEX, color=color.white,
                   scale=(random.uniform(18, 34), random.uniform(8, 16), 1),
                   position=(math.cos(a) * r, random.uniform(16, 34), math.sin(a) * r),
                   transparency=True)
        c.alpha = 0.0
        c.spd = random.uniform(0.55, 1.35)
        c.var = random.uniform(0.55, 1.0)
        w['clouds'].append(c)
    # 地面: 紫色积木小球阵
    w['balls'] = {}
    n = SURF_N
    for i in range(n):
        for j in range(n):
            x = (i - n // 2) * SPACING
            z = (j - n // 2) * SPACING
            b = Entity(model='rw_ball', color=tinted(PURPLE, random.uniform(-0.10, 0.07)),
                       scale=1.17, position=(x, 0, z))
            b.base_y = 0.0
            b.base_x = x
            b.base_z = z
            b.dip = 0.0
            w['balls'][(i, j)] = b
    w['n'] = n
    # 场地边界球墙
    w['wall'] = []
    edge = SURF_HALF + SPACING * 0.7
    k = int(round(edge / SPACING))
    for i in range(-k, k + 1):
        for j in (-k, k):
            for ly in (0, 1.15):
                b = Entity(model='rw_ball', color=tinted(PURPLE_DARK, random.uniform(-0.05, 0.08)),
                           scale=1.12, position=(i * SPACING, ly, j * SPACING))
                w['wall'].append(b)
    for j in range(-k, k + 1):
        for i in (-k, k):
            for ly in (0, 1.15):
                b = Entity(model='rw_ball', color=tinted(PURPLE_DARK, random.uniform(-0.05, 0.08)),
                           scale=1.12, position=(i * SPACING, ly, j * SPACING))
                w['wall'].append(b)
    # 洞穴地面: 暗色球 + 暗平面
    w['cave_floor'] = Entity(model='quad', color=col((0.24, 0.11, 0.44)),
                             scale=(CAVE_HALF * 2 + 2, 1, CAVE_HALF * 2 + 2),
                             rotation_x=90, y=CAVE_Y - 0.1, double_sided=True)
    w['cave_balls'] = []
    for i in range(-10, 11):
        for j in range(-10, 11):
            if (i * 5 + j * 11) % 3 == 0 or random.random() < 0.14:
                x, z = i * SPACING, j * SPACING
                b = Entity(model='rw_ball', color=tinted(PURPLE, random.uniform(-0.34, -0.20)),
                           scale=random.uniform(0.9, 1.25), position=(x, CAVE_Y, z))
                w['cave_balls'].append(b)
    for _ in range(22):   # 洞穴发光水晶
        a = random.uniform(0, math.tau)
        r = random.uniform(1.5, CAVE_HALF - 0.5)
        e = Entity(model='rw_gem', color=col(CYAN), scale=random.uniform(0.6, 1.4),
                   position=(math.cos(a) * r, CAVE_G + 0.6, math.sin(a) * r), transparency=True)
        e.alpha = 0.85
        w['cave_balls'].append(e)
    for _ in range(10):   # 萤光灯: 小球坐在暗柱上
        a = random.uniform(0, math.tau)
        r = random.uniform(2, CAVE_HALF - 1)
        x, z = math.cos(a) * r, math.sin(a) * r
        Entity(model='rw_box', color=col((0.20, 0.10, 0.36)), scale=(0.3, 1.6, 0.3),
               position=(x, CAVE_G + 0.8, z))
        lamp = Entity(model='rw_sphere_lo', color=col((1.0, 0.85, 0.45)), scale=0.5,
                      position=(x, CAVE_G + 1.75, z))
        halo = Entity(parent=lamp, model='quad', billboard=True, texture=PART_TEX,
                      color=col((1.0, 0.8, 0.4)), scale=3.2, transparency=True)
        halo.alpha = 0.5
        w['cave_balls'].append(lamp)
    ck = int(round((CAVE_HALF + 0.7) / SPACING))
    for i in range(-ck, ck + 1):
        for j in (-ck, ck):
            for ly in (CAVE_Y, CAVE_Y + 1.15):
                Entity(model='rw_ball', color=tinted(PURPLE_DARK, random.uniform(-0.10, 0.0)),
                       scale=1.12, position=(i * SPACING, ly, j * SPACING))
    for j in range(-ck, ck + 1):
        for i in (-ck, ck):
            for ly in (CAVE_Y, CAVE_Y + 1.15):
                Entity(model='rw_ball', color=tinted(PURPLE_DARK, random.uniform(-0.10, 0.0)),
                       scale=1.12, position=(i * SPACING, ly, j * SPACING))
    for _ in range(7):    # 大岩石
        a = random.uniform(0, math.tau)
        r = random.uniform(3, CAVE_HALF - 1)
        Entity(model='rw_sphere', color=col((0.30, 0.16, 0.50)), scale=random.uniform(1.8, 3.0),
               position=(math.cos(a) * r, CAVE_Y + 0.4, math.sin(a) * r))
    # 浮空平台
    w['platforms'] = []
    for (px, pz, top, ph) in PLATFORMS:
        cells = int(ph / SPACING) + 1
        for i in range(-cells, cells + 1):
            for j in range(-cells, cells + 1):
                x, z = px + i * SPACING, pz + j * SPACING
                if math.hypot(x - px, z - pz) <= ph + 0.3:
                    b = Entity(model='rw_ball', color=tinted(PURPLE, random.uniform(-0.05, 0.12)),
                               scale=1.17, position=(x, top - 0.62, z))
                    w['platforms'].append(b)
    # 弹跳球
    bx, bz = BOUNCE_POS
    w['bounce'] = Entity(model='rw_sphere', color=col((1.0, 0.45, 0.75)), scale=2.2,
                         position=(bx, 0.5, bz))
    Entity(parent=w['bounce'], model='rw_sphere_lo', color=color.white, scale=0.35,
           position=(0.3, 0.35, -0.6))
    Entity(parent=w['bounce'], model='rw_sphere_lo', color=color.white, scale=0.35,
           position=(-0.3, 0.35, -0.6))
    Entity(parent=w['bounce'], model='quad', color=color.black, scale=(0.5, 0.18, 1),
           position=(0, -0.05, -0.95), double_sided=True)
    WORLD.clear()
    WORLD.update(w)
    return w


def ball_at(x, z):
    n = WORLD['n']
    i = int(round(x / SPACING)) + n // 2
    j = int(round(z / SPACING)) + n // 2
    return WORLD['balls'].get((i, j))


def spawn_monsters(k=8):
    for _ in range(k):
        for _try in range(20):
            a = random.uniform(0, math.tau)
            r = random.uniform(5, SURF_HALF - 1)
            p = Vec3(math.cos(a) * r, SURF_Y, math.sin(a) * r)
            if (p - G.player.position).length() > 6:
                break
        G.monsters.append(Monster(p, kind=random.choice((0, 0, 1))))


def spawn_treasures():
    for (x, y, z) in SKY_TREASURES:
        G.treasures.append(Treasure(Vec3(x, y, z), beam=True))
    for (x, z) in GROUND_TREASURES:
        G.treasures.append(Treasure(Vec3(x, SURF_Y + 1.1, z), beam=True))
    for (x, z) in CAVE_TREASURES:
        G.treasures.append(Treasure(Vec3(x, CAVE_G + 1.0, z), beam=True))
    for (x, z) in CAVE_HIDDEN:
        Breakable(Vec3(x, CAVE_G, z), kind='crystal', content='treasure')
    for (x, z) in SURF_HIDDEN:
        Breakable(Vec3(x, SURF_Y, z), kind='dirt', content=None)


def clear_dynamic():
    for m in list(G.monsters):
        destroy(m)
    for t in list(G.treasures):
        destroy(t)
    for b in list(G.breakables):
        destroy(b)
    for h in list(G.holes):
        destroy(h)
    G.monsters.clear(); G.treasures.clear()
    G.breakables.clear(); G.holes.clear()


def reset_game():
    """重开一局: 动态物件 / 玩家姿态 / 地面压痕 / 粒子 / 镜头 / 天气 全部复位"""
    application.resume()                 # 保险: 万一被暂停过, 先把主循环放出来
    clear_dynamic()
    p = G.player
    p.position = Vec3(0, SURF_Y, 0)
    p.vy = 0
    p.mode = 'surface'
    p.trans_t = 0.0
    p.on_ground = True
    p.jumps = 0
    p.moving = 0.0
    p.walk_t = 0.0
    p.swing_t = -1.0
    p._hit_flag = False
    p._snapped = False
    p.body_yaw = 0.0
    p.rotation_y = 0.0
    p.model.scale = 1
    p.model.rotation_x = 0
    p.model.y = 0
    p.arm_l.rotation = (0, 0, 0)
    p.arm_r.rotation = (0, 0, 0)
    p.leg_l.rotation_x = 0
    p.leg_r.rotation_x = 0
    p.slash.enabled = False
    p.slash.alpha = 0
    G.fade = 0.0
    if FADE_QUAD is not None:
        FADE_QUAD.enabled = False
    G.cam_snap = True
    G.t = 0
    G.got = 0
    G.kills = 0
    G.cam_yaw = 0.0
    G.cam_pitch = 14.0
    G.spawn_timer = 8.0
    G.bounce_squash = 0.0
    if 'bounce' in WORLD:                # 弹弹球的挤压动画复位
        WORLD['bounce'].scale = (2.2, 2.2, 2.2)
    for b in WORLD.get('balls', {}).values():   # 地面小球的踩压/风吹偏移复位
        b.dip = 0.0
        b.y = b.base_y
        b.x = b.base_x
        b.z = b.base_z
        b.scale = (1.17, 1.17, 1.17)
    if FX is not None:                   # 上一局残留的粒子清掉
        for it in FX.items:
            it['life'] = 0.0
            it['e'].enabled = False
    if WX is not None:
        WX.reroll()
        WX.precip.clear()
        WX.flash = 0.0
        WX.tint.enabled = False
        WX.sheet.update(0.0, 0.0, 0.0)
    spawn_monsters()
    spawn_treasures()
    G.hud_dirty = True
    G.state = 'play'
    LOOK.capture(True)


def mark_hole(pos, layer):
    y = SURF_Y + 0.06 if layer == 'surface' else CAVE_G + 0.06
    c = PURPLE_DEEP if layer == 'surface' else CYAN
    e = Entity(model='rw_ring', color=col(c), scale=1.5, position=(pos.x, y, pos.z),
               double_sided=True)
    if layer == 'cave':
        e.alpha = 0.8
    G.holes.append(e)
    if len(G.holes) > 8:
        destroy(G.holes.pop(0))


def try_dive_or_rise():
    p = G.player
    if p.mode == 'surface' and p.on_ground:
        p.mode = 'dive'
        p.trans_t = 0
        SFX.play('dive')
        mark_hole(p.position, 'surface')
        FX.burst(p.position + Vec3(0, 0.4, 0), PURPLE, 18, 5, 0.7, 0.28, g=4)
        dip_balls(p.position, 1.6)
        G.hud_dirty = True
    elif p.mode == 'cave' and p.on_ground:
        p.mode = 'rise'
        p.trans_t = 0
        SFX.play('rise')
        mark_hole(p.position, 'cave')
        FX.burst(p.position + Vec3(0, 0.4, 0), CYAN, 18, 5, 0.7, 0.28, g=4)
        G.hud_dirty = True


def dip_balls(pos, radius):
    n = WORLD['n']
    ci = int(round(pos.x / SPACING)) + n // 2
    cj = int(round(pos.z / SPACING)) + n // 2
    for i in range(ci - 2, ci + 3):
        for j in range(cj - 2, cj + 3):
            b = WORLD['balls'].get((i, j))
            if b:
                d = math.hypot(b.x - pos.x, b.z - pos.z)
                if d < radius:
                    b.dip = max(b.dip, 1 - d / radius)


# ----------------------------------------------------------------------------
# HUD (PIL 贴图, 支持中文)
# ----------------------------------------------------------------------------
def dot_img(size, rgb):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([size * 0.35, size * 0.35, size * 0.65, size * 0.65],
              fill=(int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255), 200))
    return img


def soft_dot_img(size=64, rgb=(255, 255, 255)):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2.0
    for i in range(int(c), 0, -1):
        f = i / c
        a = int(255 * (1 - f) ** 1.6)
        d.ellipse([c - i, c - i, c + i, c + i],
                  fill=(int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255), a))
    return img


def streak_img(w=16, h=64, rgb=(196, 220, 255)):
    """竖直雨丝贴图: 中间亮, 两头淡出"""
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = w / 2.0
    for i in range(h):
        f = i / (h - 1.0)
        a = int(255 * math.sin(math.pi * f) ** 0.7)
        ww = max(1.0, cx * (0.30 + 0.70 * math.sin(math.pi * f)))
        d.line([(cx - ww, i), (cx + ww, i)], fill=rgb + (a,), width=1)
    return img


def wisp_img(w=64, h=16, rgb=(238, 228, 206)):
    """横向风丝 / 飞沙贴图"""
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy = h / 2.0
    for i in range(w):
        f = i / (w - 1.0)
        a = int(255 * math.sin(math.pi * f) ** 1.3)
        hh = max(1.0, cy * (0.28 + 0.72 * math.sin(math.pi * f)))
        d.line([(i, cy - hh), (i, cy + hh)], fill=rgb + (a,), width=1)
    return img


def rain_sheet_img(size=256, n=120, rgb=(205, 226, 255), seed=11):
    """可平铺的雨帘贴图: 一堆短雨丝, 上下/左右都能无缝接"""
    rnd = random.Random(seed)
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(n):
        x = rnd.uniform(0, size)
        y = rnd.uniform(0, size)
        L = rnd.uniform(10, 34)
        w = rnd.choice((1, 1, 2))
        a = rnd.randint(70, 160)
        dx = rnd.uniform(-2.5, 2.5)
        for oy in (-size, 0, size):            # 竖直方向无缝
            d.line([(x, y + oy), (x + dx, y + oy + L)], fill=rgb + (a,), width=w)
    return img


def cloud_img(size=128, rgb=(255, 255, 255), seed=7):
    """程序化云朵贴图: 若干椭圆叠加 + 高斯模糊"""
    rnd = random.Random(seed)
    w, h = size, size // 2
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(9):
        rx = rnd.uniform(0.14, 0.30) * w
        ry = rnd.uniform(0.18, 0.34) * h
        cx = rnd.uniform(0.18, 0.82) * w
        cy = rnd.uniform(0.38, 0.72) * h
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                  fill=rgb + (int(rnd.uniform(150, 235)),))
    return img.filter(ImageFilter.GaussianBlur(radius=size * 0.045))


PART_TEX = None
STREAK_TEX = None
WISP_TEX = None
CLOUD_TEX = None
RAIN_TEX = None


class HUD:
    def __init__(self):
        ar = window.aspect_ratio
        self.left = Pic(position=(-ar + 0.30, 0.40))
        self.right = Pic(position=(ar - 0.22, 0.44))
        self.hint = Pic(position=(0, -0.46))
        self.cross = Pic(position=(0.0, 0.0))
        self.cross.set_image(dot_img(26, (1, 1, 1)))
        self.overlay = Pic(position=(0, 0))
        self.toast = Pic(position=(0, 0.30))
        self.toast.enabled = False
        self._toast_t = 0.0
        self._last_left = None
        self._last_right = None
        self._last_hint = None

    def left_image(self):
        img = Image.new('RGBA', (430, 70), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        f = get_font(32)
        d.text((16, 18), f'宝藏 {G.got}/{TOTAL_TREASURE}    击杀 {G.kills}    {int(G.t)}s',
               font=f, fill=(255, 235, 160, 255), stroke_width=3, stroke_fill=(0, 0, 0, 200))
        return img

    def right_image(self):
        mode = {'surface': '地面', 'cave': '地下洞穴', 'dive': '下潜中…', 'rise': '上浮中…'}[G.player.mode]
        wname, wcol = weather_label()
        img = text_image([(mode, 30, (220, 190, 255, 255)),
                          ('天气 ' + wname, 26, wcol),
                          (f'FPS {int(G.fps)}', 24, (170, 170, 190, 255))],
                         align='right', bg=(20, 10, 35, 150))
        return img

    def show_toast(self, text, dur=2.6):
        """屏幕上方飘一条提示 (天气变化等), 结束前淡出"""
        self.toast.set_image(text_image([(text, 30, (255, 240, 200, 255))],
                                        align='center', bg=(18, 10, 34, 175)))
        self.toast.alpha = 1
        self.toast.enabled = G.state != 'title'
        self._toast_t = dur

    def update_toast(self, dt):
        if self._toast_t <= 0:
            return
        self._toast_t -= dt
        if self._toast_t <= 0:
            self.toast.enabled = False
        elif self._toast_t < 0.6:
            self.toast.alpha = self._toast_t / 0.6

    def hint_image(self, text):
        return text_image([(text, 28, (255, 255, 255, 235))], align='center',
                          bg=(15, 8, 30, 140))

    def refresh(self, force=False):
        p = G.player
        key_l = (G.got, G.kills, int(G.t))
        if force or key_l != self._last_left:
            self._last_left = key_l
            self.left.set_image(self.left_image())
            ar = window.aspect_ratio
            self.left.position = Vec2(-ar + 0.02 + self.left.scale[0] / 2, 0.42)
        key_r = (p.mode, int(G.fps), weather_label()[0])
        if force or key_r != self._last_right:
            self._last_right = key_r
            self.right.set_image(self.right_image())
            ar = window.aspect_ratio
            self.right.position = Vec2(ar - 0.02 - self.right.scale[0] / 2, 0.44)
        if p.mode == 'cave':
            hint = 'F 上浮回地面 · 左键/J 敲击水晶 · 空格 跳'
        elif p.mode == 'surface':
            hint = '第三人称: 鼠标绕角色转镜头 · WASD 移动 · 空格 跳/二段跳 · 左键/J 挥剑 · F 下潜'
        else:
            hint = '穿梭中…'
        if force or hint != self._last_hint:
            self._last_hint = hint
            self.hint.set_image(self.hint_image(hint))

    def show_overlay(self, kind):
        ar = window.aspect_ratio
        if kind == 'title':
            lines = [('圆 球 秘 境 · 寻 宝', 64, (255, 220, 120, 255)),
                     ('', 20, (0, 0, 0, 0)),
                     ('紫色圆球铺成的世界, 宝藏藏在天上与地底', 30, (230, 220, 255, 255)),
                     ('第三人称: 鼠标绕角色转镜头    W 前 S 后 A 左 D 右    Shift 奔跑', 28, (255, 255, 255, 235)),
                     ('空格 跳跃 / 二段跳(跳得更高)    左键 或 J 挥圆头剑', 28, (255, 255, 255, 235)),
                     ('F 在地面与地下之间穿梭    踩粉色弹弹球可飞天', 28, (255, 255, 255, 235)),
                     ('妖怪只会随机游荡, 不会伤害你; 没有血条, 放心探索', 28, (170, 240, 190, 235)),
                     ('天气随机变化: 晴天 / 下雨 / 下雪 / 刮风   按 1 2 3 4 或 T 手动切换', 28, (190, 220, 255, 235)),
                     ('蓝天白云在任何天气下都会显示', 26, (200, 230, 255, 225)),
                     ('Esc / P 暂停    R 重新开始    Q 退出游戏    也可以点窗口关闭按钮', 26, (205, 205, 225, 225)),
                     ('', 20, (0, 0, 0, 0)),
                     (f'集齐 {TOTAL_TREASURE} 颗宝石即胜利 —— 点击鼠标或按任意键开始', 32, (140, 255, 190, 255))]
        elif kind == 'pause':
            lines = [('已 暂 停', 56, (255, 255, 255, 255)),
                     ('P / Esc 继续    R 重新开始    Q 退出游戏', 30, (220, 220, 220, 235))]
        elif kind == 'win':
            lines = [('胜 利 !', 72, (255, 215, 90, 255)),
                     (f'集齐全部 {TOTAL_TREASURE} 颗宝石', 34, (255, 255, 255, 240)),
                     (f'用时 {int(G.t)} 秒 · 击杀妖怪 {G.kills} 只', 30, (200, 240, 255, 235)),
                     ('R 再玩一次    Q 退出游戏', 30, (140, 255, 190, 255))]
        img = text_image(lines, pad=46, line_gap=14, align='center', bg=(12, 6, 26, 205))
        self.overlay.set_image(img)
        self.overlay.enabled = True
        for p in (self.left, self.right, self.hint, self.cross, self.toast):
            p.enabled = False

    def hide_overlay(self):
        self.overlay.enabled = False
        for p in (self.left, self.right, self.hint, self.cross):
            p.enabled = True
        self.toast.enabled = self._toast_t > 0


# ----------------------------------------------------------------------------
# 镜头: 第三人称轨道 (绕角色环视)
# ----------------------------------------------------------------------------
try:                                     # 灵敏度可用环境变量 RW_MOUSE_SENS 调整
    MOUSE_SENS = clamp(float(os.environ.get('RW_MOUSE_SENS', '1.0')), 0.2, 4.0)
except Exception:
    MOUSE_SENS = 1.0
MOUSE_YAW_DEG = 0.16 * MOUSE_SENS        # 每移动 1 像素转多少度(左右)
MOUSE_PITCH_DEG = 0.15 * MOUSE_SENS      # 每移动 1 像素转多少度(上下)


class MouseLook:
    """自管鼠标视角(第三人称环视) —— 修掉"转鼠标视角乱晃"的根源

    为什么不用 Ursina 的 mouse.locked / mouse.velocity:
      * mouse.locked 会去请求系统"相对鼠标模式", 而 Panda3D 是**异步**应用的
        (实测要好几帧之后才真正切换)。切换生效前 Ursina 已经把"指针离窗口中心的
        偏移"当成速度用, 于是每一帧都甩出几十度, 视角看起来就是乱转/发抖;
      * 模式切换成功后, Ursina 仍然每帧把指针拉回中心, 和相对模式互相打架,
        产生来回抖动;
      * 它的 moving 判定用的是 x + y, 斜着移动鼠标时会整帧丢失输入。

    这里改成: 永远绝对模式, 自己算每帧像素位移; 指针快到窗口边缘时把它拉回中心,
    拉回那一帧改以中心为基准继续累加 —— 不丢位移、不跳变、可以一直转下去。
    """

    WARP_EDGE = 0.28       # 指针偏离中心超过窗口 28% 就回拉
    MAX_STEP = 90.0        # 单帧位移上限(像素): 挡住切窗口/失焦造成的一次性瞬移
    CENTER_TOL = 12.0      # 判定"回拉是否真的生效"的容差(像素)

    def __init__(self):
        self.captured = False
        self._prev = None
        self._warping = False
        self._warp_to = (0.0, 0.0)
        self.dx = 0.0
        self.dy = 0.0

    def capture(self, on):
        """进游戏=抓取鼠标(隐藏指针); 暂停/结算/标题=释放(显示指针)"""
        on = bool(on)
        self._prev = None              # 每次切换都重新对齐, 避免恢复时甩一下
        self._warping = False
        self.dx = self.dy = 0.0
        if on == self.captured:
            return
        self.captured = on
        try:
            window.set_mouse_mode(window.M_absolute)   # 始终绝对模式
            window.set_cursor_hidden(on)
            if application.base is not None:
                application.base.win.requestProperties(window)
        except Exception:
            pass

    def release(self):
        self.capture(False)

    def poll(self):
        """读取本帧鼠标位移(像素), 返回 (dx, dy); 未抓取时恒为 (0, 0)"""
        self.dx = self.dy = 0.0
        if not self.captured:
            return (0.0, 0.0)
        base = application.base
        win = getattr(base, 'win', None) if base is not None else None
        if win is None:
            return (0.0, 0.0)
        try:
            md = win.getPointer(0)
            x, y = float(md.getX()), float(md.getY())
            w = float(win.getXSize()) or 1.0
            h = float(win.getYSize()) or 1.0
        except Exception:
            self._prev = None
            return (0.0, 0.0)

        if self._prev is None:                     # 刚抓取/刚回拉: 只对齐不转视角
            self._prev = (x, y)
            return (0.0, 0.0)

        if self._warping:                          # 上一帧把指针拉回了窗口中心
            tx, ty = self._warp_to
            self._warping = False
            if abs(x - tx) <= self.CENTER_TOL and abs(y - ty) <= self.CENTER_TOL:
                dx, dy = x - tx, y - ty            # 回拉生效: 以中心为基准继续算
            else:
                dx, dy = 0.0, 0.0                  # 系统忽略了回拉: 仅重新对齐
            self._prev = (x, y)
        else:
            dx, dy = x - self._prev[0], y - self._prev[1]
            self._prev = (x, y)

        # 指针快跑出窗口就拉回中心, 这样才能一直朝一个方向转
        cx, cy = w * 0.5, h * 0.5
        if abs(x - cx) > w * self.WARP_EDGE or abs(y - cy) > h * self.WARP_EDGE:
            try:
                if win.movePointer(0, int(cx), int(cy)):
                    self._warp_to = (float(int(cx)), float(int(cy)))
                    self._warping = True
            except Exception:
                self._warping = False

        self.dx = clamp(dx, -self.MAX_STEP, self.MAX_STEP)
        self.dy = clamp(dy, -self.MAX_STEP, self.MAX_STEP)
        return (self.dx, self.dy)


LOOK = MouseLook()          # 全局鼠标视角控制器
CAM_DIST = 5.4         # 镜头到角色的轨道距离
CAM_DIST_CAVE = 4.2    # 洞穴里空间矮, 拉近一点
CAM_TARGET_Y = 1.35    # 镜头注视点离脚底的高度
CAM_PITCH_MIN = -42.0  # 仰视上限(看天上的宝石)
CAM_PITCH_MAX = 62.0   # 俯视上限


def _orbit_pos(target, fwd, dist, cave):
    """沿轨道线从近到远找最远可用机位: 撞地面/洞顶/场墙就提前停下(=自动拉近)"""
    best = target - fwd * 1.1
    steps = 10
    for i in range(2, steps + 1):
        c = target - fwd * (dist * i / steps)
        if cave:
            if not (CAVE_G + 0.35 <= c.y <= CAVE_CEIL + 0.55
                    and abs(c.x) <= CAVE_HALF + 1.6 and abs(c.z) <= CAVE_HALF + 1.6):
                break
        else:
            if (c.y < SURF_Y + 0.35 or abs(c.x) > SURF_HALF + 2.5
                    or abs(c.z) > SURF_HALF + 2.5):
                break
        best = c
    # 兜底: 机位无论如何都夹在合法盒里
    if cave:
        best.y = clamp(best.y, CAVE_G + 0.35, CAVE_CEIL + 0.55)
        best.x = clamp(best.x, -CAVE_HALF - 1.6, CAVE_HALF + 1.6)
        best.z = clamp(best.z, -CAVE_HALF - 1.6, CAVE_HALF + 1.6)
    else:
        best.y = max(best.y, SURF_Y + 0.35)
        best.x = clamp(best.x, -SURF_HALF - 2.5, SURF_HALF + 2.5)
        best.z = clamp(best.z, -SURF_HALF - 2.5, SURF_HALF + 2.5)
    return best


def update_camera(dt):
    """第三人称: 镜头在角色身后绕轨道环视, 鼠标转的是轨道角度"""
    p = G.player
    mdx, mdy = LOOK.poll()                 # 每帧都要取走位移, 免得攒着一次甩出去
    turning = (mdx != 0.0 or mdy != 0.0) and G.state == 'play'
    if turning:
        # 单位陷阱: G.cam_yaw 是**弧度**(要喂给 sin/cos), G.cam_pitch 是**度**。
        # 旧代码把"度"的灵敏度直接加到弧度的 yaw 上, 相当于放大了 57.3 倍,
        # 鼠标动 10 像素镜头就甩 100 多度 —— 这就是"视角混乱晃动"的根源。
        G.cam_yaw += math.radians(mdx * MOUSE_YAW_DEG)
        # 屏幕坐标 y 向下为正: 鼠标往上推(dy<0)=抬头=pitch 变小
        G.cam_pitch = clamp(G.cam_pitch + mdy * MOUSE_PITCH_DEG,
                            CAM_PITCH_MIN, CAM_PITCH_MAX)
        G.cam_yaw = (G.cam_yaw + math.pi) % math.tau - math.pi   # 转多久都不丢精度
    # 走路时的轻微起伏
    bob = 0.0
    if p.on_ground and p.moving > 0.05 and p.mode in ('surface', 'cave'):
        bob = math.sin(p.walk_t) * 0.045 * p.moving
    target = p.position + Vec3(0, CAM_TARGET_Y + bob, 0)
    cave = p.mode == 'cave' or (p.mode == 'rise' and p.trans_t > 0.5) \
        or (p.mode == 'dive' and p.trans_t > 0.5)
    dist = CAM_DIST_CAVE if p.mode == 'cave' else CAM_DIST
    spin = 0.0
    if p.mode in ('dive', 'rise'):        # 穿梭时镜头翻滚 + 拉近
        f = min(1, p.trans_t / 0.9)
        spin = 360 * f if p.mode == 'dive' else -360 * f
        dist = lerp(dist, 3.4, math.sin(math.pi * f))
    pitch = G.cam_pitch
    windy = (WX is not None and WX.wind_str > 0.06 and WX.vis > 0.5
             and G.state == 'play')
    if windy:
        # 大风: 镜头轻微侧倾 + 抖动, 站着不动也能感觉到风(幅度已调小, 不与鼠标转向打架)
        s = WX.wind_str * WX.vis
        tt = WX.clock
        spin += math.sin(tt * 1.9) * 0.45 * s + math.sin(tt * 0.71 + 1.2) * 0.22 * s
        pitch += math.sin(tt * 1.31 + 0.6) * 0.35 * s
    pr = math.radians(pitch)
    fwd = Vec3(math.sin(G.cam_yaw) * math.cos(pr), -math.sin(pr),
               math.cos(G.cam_yaw) * math.cos(pr))
    desired = _orbit_pos(target, fwd, dist, cave)
    # 轨道被墙/地面截得很短时把镜头吊高一点, 避免角色糊满整屏
    d_left = (target - desired).length()
    if d_left < 3.2:
        desired.y += min(0.8, (3.2 - d_left) * 0.30)
    if G.cam_snap:
        G.cam_snap = False
        camera.position = desired
    else:
        # 转视角时镜头几乎贴着轨道走(否则机位滞后会让画面"游"、看着发晕);
        # 不转的时候留一点平滑, 消化角色走动/轨道回缩带来的位移
        k = 1 - math.exp(-(34.0 if turning else 20.0) * dt)
        camera.position = camera.position + (desired - camera.position) * k
    if windy:
        s = WX.wind_str * WX.vis
        tt = WX.clock
        camera.x += math.sin(tt * 2.7) * 0.016 * s
        camera.y += math.sin(tt * 2.13) * 0.011 * s
    camera.rotation = (pitch, math.degrees(G.cam_yaw), spin)
    # 穿梭淡入淡出遮罩
    if FADE_QUAD is not None:
        a = G.fade
        if a > 0.004:
            FADE_QUAD.enabled = True
            FADE_QUAD.color = Color(0.02, 0.0, 0.06, min(1.0, a))
        elif FADE_QUAD.enabled:
            FADE_QUAD.enabled = False


def jump():
    p = G.player
    if G.state != 'play' or p.mode in ('dive', 'rise'):
        return
    if p.on_ground:
        p.vy = 10.2
        p.on_ground = False
        p.jumps = 1
        SFX.play('jump')
        FX.burst(p.position, PURPLE, 6, 3, 0.4, 0.16, g=6)
    elif p.jumps < 2:
        p.vy = 13.4                      # 二段跳大幅加高, 明显蹿升
        p.jumps = 2
        SFX.play('djump')
        FX.burst(p.position + Vec3(0, 0.4, 0), CYAN, 18, 5.5, 0.6, 0.24, g=3, up=1.6)
        ring = Entity(model='rw_ring', color=col(CYAN), position=p.position + Vec3(0, 0.15, 0),
                      scale=0.6, transparency=True, double_sided=True)
        ring.alpha = 0.9
        ring.animate('scale', Vec3(3.4, 1, 3.4), duration=0.42, curve=curve.out_expo)
        ring.fade_out(duration=0.42)
        destroy(ring, delay=0.5)


def start_game():
    G.state = 'play'
    G.cam_snap = True
    LOOK.capture(True)
    HUDI.hide_overlay()
    SFX.start_music()
    SFX.play('ui')


def toggle_pause():
    """暂停 / 继续

    只用 G.state 当闸门, **绝不能**调 application.pause():
    Ursina 一旦 paused, `__main__.input` 就不再被调用(见 ursina/main.py),
    于是暂停之后 Esc / R / Q 全部失灵 —— 既不能继续也不能重开, 只能强杀进程。
    """
    if G.state == 'play':
        G.state = 'pause'
        LOOK.capture(False)
        HUDI.show_overlay('pause')
        SFX.play('ui', volume=0.5)
    elif G.state == 'pause':
        G.state = 'play'
        LOOK.capture(True)
        HUDI.hide_overlay()
        SFX.play('ui', volume=0.5)


def restart_game():
    """重新开始一局: 游戏中 / 暂停中 / 胜利界面 都能用"""
    reset_game()
    HUDI.hide_overlay()
    HUDI.refresh(force=True)
    if SFX is not None:
        SFX.play('ui')
    print('GAME RESTART', flush=True)


def _force_quit():
    """硬退出兜底: 任何异常路径都能真正结束进程"""
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(0)


def _window_open():
    """窗口是否还开着(点标题栏关闭按钮时会变 False)"""
    try:
        base = application.base
        if base is None or base.win is None:
            return False
        return bool(base.win.getProperties().getOpen())
    except Exception:
        return True


def quit_game():
    """退出游戏(干净, 而且必定退得掉)

    1) 释放鼠标 + application.resume(): Ursina 暂停时 invoke/Sequence 不执行,
       直接 application.quit() 会永远卡住;
    2) base.userExit() 关掉 Panda 主循环, app.run() 抛 SystemExit 正常收尾;
    3) 1 秒后 os._exit 兜底, 万一 SystemExit 被框架吞掉也能退出。
    """
    if G.state == 'quit':
        return
    G.state = 'quit'
    print('GAME QUIT', flush=True)
    try:
        LOOK.capture(False)
    except Exception:
        pass
    try:
        application.resume()
    except Exception:
        pass
    try:
        if SFX is not None:
            for a in list(SFX.amb.values()):
                a.volume = 0
            if SFX.music is not None:
                SFX.music.stop()
    except Exception:
        pass
    t = threading.Timer(1.0, _force_quit)
    t.daemon = True
    t.start()
    try:
        base = application.base
        if base is not None:
            base.userExit()
    except SystemExit:
        raise
    except Exception:
        pass
    _force_quit()


# ----------------------------------------------------------------------------
# 输入
# ----------------------------------------------------------------------------
def input(key):
    if G.state == 'quit':
        return
    # 菜单类界面(标题/暂停/结算)按 Q 退出; 游戏进行中按 Q 不退, 免得误触
    if key == 'q' and G.state in ('title', 'pause', 'win', 'lose'):
        quit_game()
        return
    if G.state == 'title':
        if key in ('left mouse down', 'space', 'enter', 'w', 'j'):
            start_game()
        elif key == 'escape':
            quit_game()
        return
    if key in ('p', 'escape'):
        if G.state in ('play', 'pause'):
            toggle_pause()
        else:                      # 结算界面: Esc = 退出
            quit_game()
        return
    if key == 'r' and G.state in ('play', 'pause', 'win', 'lose'):
        restart_game()             # 暂停中也能重开(旧版本这里会永久卡死)
        return
    if G.state != 'play':
        return
    if key == 'space':
        jump()
    elif key in ('left mouse down', 'j'):
        G.player.attack()
    elif key == 'f':
        try_dive_or_rise()
    elif key in ('1', '2', '3', '4'):
        WX.set_weather(WEATHER_ORDER[int(key) - 1])
    elif key == 't':
        WX.cycle()


# ----------------------------------------------------------------------------
# 主循环
# ----------------------------------------------------------------------------
def collect_checks():
    p = G.player
    head = p.position + Vec3(0, 1.2, 0)
    for t in list(G.treasures):
        if (t.world_position - head).length() < 1.9:
            G.treasures.remove(t)
            G.got += 1
            SFX.play('gem')
            FX.burst(t.world_position, GOLD, 26, 7, 0.9, 0.3, g=5)
            destroy(t)
            G.hud_dirty = True
            if G.got >= TOTAL_TREASURE:
                G.game_over(True)


def update_balls(dt, t):
    p = G.player
    if p.mode not in ('surface',):
        return
    wind_sway = (WX.wind_str * WX.vis * 0.085) if WX is not None else 0.0
    n = WORLD['n']
    ci = int(round(p.x / SPACING)) + n // 2
    cj = int(round(p.z / SPACING)) + n // 2
    for i in range(ci - 2, ci + 3):
        for j in range(cj - 2, cj + 3):
            b = WORLD['balls'].get((i, j))
            if b is None:
                continue
            d = math.hypot(b.x - p.x, b.z - p.z)
            if b.dip > 0:
                b.dip = max(0, b.dip - dt * 1.6)
            press = max(0, 1 - d / 1.5) * (0.6 + 0.4 * p.moving)
            k = b.dip * 0.9 + press * 0.22
            b.y = b.base_y - k * 0.55 + math.sin(t * 1.6 + (i + j) * 0.7) * 0.02
            s = 1.17 * (1 - 0.10 * k)
            b.scale = (s, s * (1 - 0.16 * k), s)
            # 大风: 脚边的紫色小球像草一样被吹得晃
            if wind_sway > 0.0:
                ph = math.sin(t * 2.4 + i * 0.9 + j * 0.55) * wind_sway
                b.x = b.base_x + WX.wind_dir[0] * ph
                b.z = b.base_z + WX.wind_dir[1] * ph
            elif b.x != b.base_x or b.z != b.base_z:
                b.x = b.base_x
                b.z = b.base_z


def game_update():
    if G.state == 'quit':
        return
    dt = min(time.dt, 0.05)
    G.frame += 1
    if G.frame % 15 == 0 and not _window_open():
        quit_game()                      # 点了标题栏关闭按钮 / 系统要求退出
        return
    G.fps_acc += time.dt
    G.fps_n += 1
    if G.fps_acc >= 0.5:
        G.fps = G.fps_n / G.fps_acc
        G.fps_acc = 0
        G.fps_n = 0
        G.hud_dirty = True
    if G.state == 'play':
        G.t += dt
        p = G.player
        p.update(dt)
        for m in list(G.monsters):
            m.update(dt)
        for t in list(G.treasures):
            t.update(dt)
        for b in list(G.breakables):
            b.update(dt)
        collect_checks()
        update_balls(dt, G.t)
        if G.bounce_squash > 0:
            G.bounce_squash -= dt
            f = max(0, G.bounce_squash / 0.3)
            WORLD['bounce'].scale = (2.2 * (1 + 0.25 * f), 2.2 * (1 - 0.35 * f), 2.2 * (1 + 0.25 * f))
        G.spawn_timer -= dt
        if G.spawn_timer <= 0:
            G.spawn_timer = 10.0
            alive = sum(1 for m in G.monsters if not m.dead)
            if alive < 8:
                spawn_monsters(1)
        if G.hud_dirty:
            G.hud_dirty = False
            HUDI.refresh()
    FX.update(dt)
    if WX is not None:
        WX.update(dt)
        HUDI.update_toast(dt)
    update_camera(dt)
    if SELFTEST:
        selftest_step()


def update():
    game_update()


def Game_game_over(self, win):
    if self.state != 'play':
        return
    self.state = 'win'
    LOOK.capture(False)
    SFX.play('win')
    HUDI.show_overlay('win')


Game.game_over = Game_game_over


# ----------------------------------------------------------------------------
# 自检模式 (RW_SELFTEST=1): 自动操作并截图, 用于无人值守验证
# ----------------------------------------------------------------------------
ST_SHOTS = {5: 'title', 45: 'djump', 120: 'a', 126: 'rain_s1', 134: 'rain_s2',
            145: 'rain_up', 156: 'swing', 260: 'b', 430: 'c',
            615: 'd', 620: 'wind', 672: 'e', 695: 'win', 478: 'snow_up',
            702: 'restart', 722: 'paused'}
ST_WEATHER = {90: ('rain', True), 250: ('wind', False), 425: ('snow', True),
              560: ('wind', True), 640: ('clear', True)}


def selftest_step():
    f = G.frame
    if f in ST_WEATHER and WX is not None:      # 把四种天气都跑一遍并截图
        kind, instant = ST_WEATHER[f]
        WX.set_weather(kind, instant=instant, announce=False)
    if f in (135, 470):                          # 抬头看天, 截云/雨/雪
        G.cam_pitch = -30
    elif f in (150, 486):
        G.cam_pitch = 8
    if f == 20:
        p0 = G.player
        p0.position = Vec3(0, SURF_Y, 0)
        G.cam_snap = True
        p0.vy = 0
        p0.on_ground = True
        p0.jumps = 0
        G._dj_max = SURF_Y
    elif f == 22:
        jump()
    elif f == 32:
        jump()
    elif f == 80:
        print('DJUMP MAX Y = %.2f (ground %.2f, gain %.2f)' %
              (G._dj_max, SURF_Y, G._dj_max - SURF_Y), flush=True)
    if 22 <= f <= 79:
        G._dj_max = max(G._dj_max, G.player.y)
    if f == 10:
        start_game()
    elif f == 30:
        G.cam_yaw = math.pi
    elif f == 40:
        held_keys['w'] = True
    elif f == 90:
        jump()
    elif f == 100:
        jump()
    elif f == 110:
        held_keys['w'] = False
        G.cam_yaw = 0.0
    elif f == 150:
        G.player.attack()
    elif f == 200:
        try_dive_or_rise()
    elif f == 210:
        G.cam_yaw = 0.0
    elif f == 280:
        held_keys['w'] = True
    elif f == 330:
        G.player.attack()
    elif f == 380:
        held_keys['w'] = False
    elif f == 420:
        try_dive_or_rise()
    elif f == 480:
        G.cam_yaw = 0.9
    elif f == 520:
        jump()
    elif f == 550:
        if G.monsters:
            m = G.monsters[0]
            fw = Vec3(math.sin(G.cam_yaw), 0, math.cos(G.cam_yaw))
            m.position = G.player.position + fw * 2.0
            m.position.y = SURF_Y
    elif f in (555, 580, 605):
        G.player.attack()
    elif f == 620:
        held_keys['d'] = True
    elif f == 640:
        held_keys['d'] = False
        gt = GROUND_TREASURES[0]
        G.player.position = Vec3(gt[0], SURF_Y, gt[1])
        G.cam_snap = True
    elif f == 660:
        G.cam_pitch = -34
    elif f == 685:
        G.got = TOTAL_TREASURE
        G.game_over(True)
    # --- 胜利后重开一局 + 鼠标视角自检 + 暂停中重开 + 暂停中退出 ---
    elif f == 690:
        for kk in ('w', 'a', 's', 'd', 'shift'):
            held_keys[kk] = False
        input('r')                                  # 胜利界面按 R 重开
    elif f == 700:
        win = application.base.win
        win.movePointer(0, int(win.getXSize() / 2), int(win.getYSize() / 2))
        LOOK._prev = None
        G.cam_yaw = 0.0
        G.cam_pitch = 14.0
        G._st_yaw0 = G.cam_yaw
        wp = win.getProperties()
        print('WINDOW size=%dx%d fullscreen=%s undecorated=%s open=%s captured=%s'
              % (win.getXSize(), win.getYSize(), wp.getFullscreen(),
                 wp.getUndecorated(), wp.getOpen(), LOOK.captured), flush=True)
    elif 701 <= f <= 712:                           # 每帧把指针右移 14 像素
        win = application.base.win
        md = win.getPointer(0)
        win.movePointer(0, int(md.getX()) + 14, int(md.getY()))
        if f > 701 and (LOOK.dx != 14.0 or LOOK.dy != 0.0):   # 位移必须逐帧精确对上
            print('MOUSELOOK-BAD f=%d dx=%.1f dy=%.1f' % (f, LOOK.dx, LOOK.dy), flush=True)
    elif f == 713:
        got = math.degrees((G.cam_yaw - G._st_yaw0 + math.pi) % math.tau - math.pi)
        exp = 12 * 14 * MOUSE_YAW_DEG
        print('MOUSELOOK frames=12 step=14px got=%.2fdeg exp=%.2fdeg err=%.3f pitch=%.2f'
              % (got, exp, abs(got - exp), G.cam_pitch), flush=True)
    elif f == 720:
        input('escape')                             # 暂停
        print('PAUSE state=%s app_paused=%s captured=%s'
              % (G.state, application.paused, LOOK.captured), flush=True)
    elif f == 726:
        input('r')                                  # 暂停中重开(旧版本这里永久卡死)
        print('RESTART-FROM-PAUSE state=%s app_paused=%s got=%d treasures=%d monsters=%d captured=%s'
              % (G.state, application.paused, G.got, len(G.treasures),
                 len(G.monsters), LOOK.captured), flush=True)
    elif f == 732:
        input('escape')                             # 再暂停一次
        print('SELFTEST DONE state=%s got=%d kills=%d fps=%.1f'
              % (G.state, G.got, G.kills, G.fps), flush=True)
    elif f == 736:
        print('QUIT-FROM-PAUSE ...', flush=True)
        input('q')                                  # 暂停中退出(旧版本退不掉)
    elif f == 800:                                  # 兜底
        application.quit()
    if f in ST_SHOTS:
        from panda3d.core import Filename
        application.base.win.saveScreenshot(Filename('/tmp/rwtest/play_%s.png' % ST_SHOTS[f]))
        print('SHOT', ST_SHOTS[f], 'state', G.state, 'mode', G.player.mode,
              'pos', tuple(round(v, 1) for v in G.player.position),
              'got', G.got, 'fps', round(G.fps, 1),
              'wx', WX.kind if WX else '-', 'blend', round(WX.blend, 2) if WX else 1.0,
              'wind', round(WX.wind_str, 2) if WX else 0.0, flush=True)
    # 退出/收尾流程见上面 f == 732 / 736 分支


# ----------------------------------------------------------------------------
# 启动
# ----------------------------------------------------------------------------
def main():
    global FX, SFX, HUDI, WX, PART_TEX, STREAK_TEX, WISP_TEX, CLOUD_TEX, RAIN_TEX
    register_meshes()
    # 默认带标题栏的窗口模式: 系统关闭按钮能直接退出游戏。
    # (旧版是"无边框 + 全屏 + 藏鼠标", 根本没有关闭按钮, 玩家退不出去)
    want_fullscreen = os.environ.get('RW_FULLSCREEN', '') not in ('', '0')
    app = Ursina(title='圆球秘境 · 寻宝  (Round World Treasure Hunt)',
                 development_mode=False, vsync=True,
                 borderless=False, fullscreen=want_fullscreen,
                 size=(1280, 720))
    window.color = col((0.05, 0.02, 0.09))
    try:
        if not want_fullscreen:
            window.size = (1280, 720)
    except Exception:
        pass
    camera.clip_plane_distance = (0.1, 220)
    camera.fov = 72
    try:
        mouse.traverse_target = None     # 场景里没有碰撞体, 省掉每帧射线遍历
    except Exception:
        pass

    application.asset_folder = Path(GAME_DIR)
    PART_TEX = Texture(soft_dot_img(64))
    STREAK_TEX = Texture(streak_img())
    WISP_TEX = Texture(wisp_img())
    CLOUD_TEX = Texture(cloud_img())
    RAIN_TEX = Texture(rain_sheet_img())
    RAIN_TEX.repeat = True
    SFX = SoundBank(build_sounds())
    random.seed(20260926)          # 世界布局与"这次有没有新生成音效"无关, 保持稳定
    SFX.preload_ambients(('rain', 'wind', 'snow'))
    FX = Particles()
    build_world()
    WX = WeatherSystem()
    G.player = Player()
    HUDI = HUD()
    global FADE_QUAD
    FADE_QUAD = Entity(parent=camera, model='quad', scale=16.0, position=(0, 0, 0.36),
                       color=Color(0.02, 0.0, 0.06, 0.0), transparency=True)
    FADE_QUAD.setDepthWrite(False)
    FADE_QUAD.enabled = False
    reset_game()
    G.state = 'title'
    LOOK.capture(False)                  # 标题界面显示鼠标, 方便点开始/点关闭
    HUDI.show_overlay('title')
    HUDI.refresh(force=True)

    app.run()


if __name__ == '__main__':
    main()
