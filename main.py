import pygame
import json
import os
import time
import random
import math
import socket
import threading
import queue
import base64
import struct

from pathlib import Path

pygame.init()

INFO = pygame.display.Info()
WIDTH, HEIGHT = INFO.current_w, INFO.current_h
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("BREAKCUBE")

CLOCK = pygame.time.Clock()
FPS = 60

# Шрифт берётся из папки fonts рядом с .py файлом:
# ./fonts/LavishlyYours-Regular.ttf
FONT_PATH = Path(__file__).parent / "fonts" / "Italianno-Regular.ttf"

if FONT_PATH.exists():
    FONT = pygame.font.Font(str(FONT_PATH), 40)
    SMALL = pygame.font.Font(str(FONT_PATH), 28)
    BIG = pygame.font.Font(str(FONT_PATH), 84)
    HUGE = pygame.font.Font(str(FONT_PATH), 120)
else:
    # fallback, чтобы игра не падала, если файла шрифта нет
    FONT = pygame.font.SysFont("arial", 40, bold=True)
    SMALL = pygame.font.SysFont("arial", 28, bold=True)
    BIG = pygame.font.SysFont("arial", 84, bold=True)
    HUGE = pygame.font.SysFont("arial", 120, bold=True)

LEVEL_FILE = "breakcube_level.json"
ACCOUNT_FILE = "breakcube_account.json"
SETTINGS_FILE = "breakcube_settings.json"
SERVER_HOST = "when-jury.gl.at.ply.gg"
SERVER_PORT = 33699

# Local fallback. If server.py is running on the same PC, this fixes endless loading.
LOCAL_SERVER_HOST = "127.0.0.1"
LOCAL_SERVER_PORT = 8484
SONG_CACHE_DIR = Path(__file__).resolve().parent / "songs"
SONG_CACHE_DIR.mkdir(parents=True, exist_ok=True)

GRID = 50
PANEL_H = 120

BLACK = (0, 0, 0)
WHITE = (235, 235, 235)
DARK = (8, 8, 11)
DARK2 = (18, 18, 23)
RED = (255, 0, 0)
PLAYER_RED = (230, 0, 0)
GRAY = (105, 105, 112)
PINK = (255, 70, 180)
GREEN = (0, 220, 85)
YELLOW = (245, 220, 70)

DRAW_TOOLS = {"block", "spike", "erase"}

def clamp(v, a, b):
    return max(a, min(b, v))

def snap_floor(v):
    return int(v // GRID) * GRID

def rect_of(obj):
    return pygame.Rect(obj["x"], obj["y"], GRID, GRID)

def default_level():
    return {
        "name": "Level 1",
        "objects": [
            {"type": "start", "x": 100, "y": 450},
            {"type": "block", "x": 100, "y": 550},
            {"type": "block", "x": 150, "y": 550},
            {"type": "block", "x": 200, "y": 550},
            {"type": "block", "x": 250, "y": 550},
            {"type": "block", "x": 300, "y": 550},
            {"type": "spike", "x": 400, "y": 500},
            {"type": "block", "x": 550, "y": 500},
            {"type": "block", "x": 600, "y": 500},
            {"type": "finish", "x": 750, "y": 450},
        ]
    }

def normalize_level(level):
    if not isinstance(level, dict):
        level = default_level()

    objects = level.get("objects", [])
    clean = []
    used_single = {"start": False, "finish": False}
    occupied = set()

    for obj in objects:
        t = obj.get("type", "block")
        if t not in ("block", "spike", "finish", "start"):
            continue

        x = snap_floor(int(obj.get("x", 0)))
        y = snap_floor(int(obj.get("y", 0)))

        if t in ("start", "finish"):
            if used_single[t]:
                continue
            used_single[t] = True
            clean.append({"type": t, "x": x, "y": y})
        else:
            key = (x, y)
            if key in occupied:
                clean = [o for o in clean if not (o["x"] == x and o["y"] == y and o["type"] in ("block", "spike"))]
            occupied.add(key)
            clean.append({"type": t, "x": x, "y": y})

    if not any(o["type"] == "start" for o in clean):
        clean.append({"type": "start", "x": 100, "y": 450})
    if not any(o["type"] == "finish" for o in clean):
        clean.append({"type": "finish", "x": 750, "y": 450})

    return {"name": str(level.get("name", "Level 1")), "objects": clean, "song": str(level.get("song", ""))}

def load_level():
    if not os.path.exists(LEVEL_FILE):
        lvl = default_level()
        save_level(lvl)
        return lvl
    try:
        with open(LEVEL_FILE, "r", encoding="utf-8") as f:
            return normalize_level(json.load(f))
    except Exception:
        lvl = default_level()
        save_level(lvl)
        return lvl

def save_level(level):
    level = normalize_level(level)
    with open(LEVEL_FILE, "w", encoding="utf-8") as f:
        json.dump(level, f, ensure_ascii=False, indent=2)

def load_account():
    if not os.path.exists(ACCOUNT_FILE):
        return None
    try:
        with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        name = str(data.get("name", "")).strip()
        token = str(data.get("token", "")).strip()
        if name and token:
            return {"name": name, "token": token}
    except Exception:
        pass
    return None

def save_account(name, token):
    name = str(name).strip()
    token = str(token).strip()
    if not name or not token:
        return None
    data = {"name": name, "token": token}
    with open(ACCOUNT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

def clear_account():
    try:
        if os.path.exists(ACCOUNT_FILE):
            os.remove(ACCOUNT_FILE)
    except Exception:
        pass

def load_settings():
    default = {"volume": 0.7}
    if not os.path.exists(SETTINGS_FILE):
        return default
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"volume": clamp(float(data.get("volume", 0.7)), 0.0, 1.0)}
    except Exception:
        return default

def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

class Button:
    def __init__(self, text, rect, action=None):
        self.text = text
        self.rect = pygame.Rect(rect)
        self.action = action

    def draw(self, selected=False):
        mouse = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse)
        fill = (48, 48, 56) if hover else (22, 22, 28)
        if selected:
            fill = (75, 75, 86)
        pygame.draw.rect(SCREEN, fill, self.rect)
        pygame.draw.rect(SCREEN, RED if hover or selected else GRAY, self.rect, 3)
        txt = SMALL.render(self.text, True, WHITE)
        SCREEN.blit(txt, txt.get_rect(center=self.rect.center))

    def hit(self, pos):
        return self.rect.collidepoint(pos)

class FxSquare:
    def __init__(self):
        self.reset(True)

    def reset(self, anywhere=False):
        size = random.choice([4, 6, 8, 10, 14, 20, 28, 38, 52, 70])
        self.rect = pygame.Rect(0, 0, size, size)
        self.rect.x = random.randint(-200, WIDTH + 200) if anywhere else random.choice([-150, WIDTH + 150])
        self.rect.y = random.randint(-150, HEIGHT + 150)
        self.vx = random.uniform(-24, 24)
        self.vy = random.uniform(-18, 18)
        if abs(self.vx) < 5:
            self.vx = random.choice([-11, 11])
        if abs(self.vy) < 4:
            self.vy = random.choice([-8, 8])
        self.life = random.uniform(0.15, 1.2)
        self.color = random.choice([RED, WHITE, GRAY, PINK, GREEN, (90, 0, 0), (40, 40, 48)])
        self.outline = random.random() < 0.45

    def update(self, dt):
        self.rect.x += int(self.vx)
        self.rect.y += int(self.vy)
        self.life -= dt
        if (
            self.life <= 0 or
            self.rect.right < -260 or
            self.rect.left > WIDTH + 260 or
            self.rect.bottom < -220 or
            self.rect.top > HEIGHT + 220
        ):
            self.reset(False)

    def draw(self):
        flash = random.randint(30, 255)
        c = tuple(clamp(int(v * flash / 255), 0, 255) for v in self.color)
        if self.outline:
            pygame.draw.rect(SCREEN, c, self.rect, random.choice([1, 2, 3]))
        else:
            pygame.draw.rect(SCREEN, c, self.rect)
            pygame.draw.rect(SCREEN, BLACK, self.rect, 2)

def make_fx():
    return [FxSquare() for _ in range(160)]

def draw_fx_bg(fx):
    SCREEN.fill(BLACK)
    dt = CLOCK.get_time() / 1000

    for s in fx:
        s.update(dt)
        s.draw()

    for _ in range(65):
        x = random.randint(0, WIDTH)
        y = random.randint(0, HEIGHT)
        w = random.choice([2, 4, 8, 16, 32, 80, 160])
        h = random.choice([1, 2, 3, 6, 12])
        color = random.choice([RED, WHITE, GRAY, PINK, (80, 0, 0)])
        if random.random() < 0.55:
            pygame.draw.rect(SCREEN, color, (x, y, w, h))
        else:
            pygame.draw.rect(SCREEN, color, (x, y, w, h), 1)

    for _ in range(random.randint(4, 12)):
        y = random.randint(0, HEIGHT)
        strip = pygame.Surface((WIDTH, random.choice([1, 2, 4, 8])), pygame.SRCALPHA)
        strip.fill((255, 0, 0, random.randint(18, 115)))
        SCREEN.blit(strip, (0, y))

    if random.random() < 0.75:
        dark = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        dark.fill((0, 0, 0, random.randint(35, 160)))
        SCREEN.blit(dark, (0, 0))

    for _ in range(random.randint(2, 7)):
        if random.random() < 0.65:
            pygame.draw.rect(
                SCREEN,
                BLACK,
                (
                    random.randint(0, WIDTH),
                    random.randint(0, HEIGHT),
                    random.choice([40, 90, 160, 280, 440]),
                    random.choice([8, 16, 32, 70])
                )
            )

    if random.random() < 0.45:
        pygame.draw.rect(SCREEN, RED, (0, random.randint(0, HEIGHT), WIDTH, random.choice([2, 4, 8, 16])))

    if random.random() < 0.35:
        pygame.draw.rect(SCREEN, RED, (random.randint(0, WIDTH), 0, random.choice([2, 4, 8, 12]), HEIGHT))

    if random.random() < 0.45:
        pad = random.randint(15, 90)
        pygame.draw.rect(SCREEN, RED, (pad, pad, WIDTH - pad * 2, HEIGHT - pad * 2), random.choice([2, 3, 5]))

    vignette = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    pygame.draw.rect(vignette, (0, 0, 0, 130), (0, 0, WIDTH, 90))
    pygame.draw.rect(vignette, (0, 0, 0, 155), (0, HEIGHT - 115, WIDTH, 115))
    pygame.draw.rect(vignette, (0, 0, 0, 105), (0, 0, 95, HEIGHT))
    pygame.draw.rect(vignette, (0, 0, 0, 105), (WIDTH - 95, 0, 95, HEIGHT))
    SCREEN.blit(vignette, (0, 0))

def draw_title(text, y):
    for _ in range(2):
        shadow = HUGE.render(text, True, RED)
        SCREEN.blit(shadow, shadow.get_rect(center=(WIDTH // 2 + random.randint(-5, 5), y + random.randint(-4, 4))))
    title = HUGE.render(text, True, WHITE)
    SCREEN.blit(title, title.get_rect(center=(WIDTH // 2, y)))

def draw_input(rect, text, placeholder):
    pygame.draw.rect(SCREEN, (16, 16, 22), rect)
    pygame.draw.rect(SCREEN, RED, rect, 3)
    shown = text if text else placeholder
    color = WHITE if text else GRAY
    txt = FONT.render(shown, True, color)
    SCREEN.blit(txt, (rect.x + 16, rect.y + rect.h // 2 - txt.get_height() // 2))

def draw_password_input(rect, text, placeholder):
    pygame.draw.rect(SCREEN, (16, 16, 22), rect)
    pygame.draw.rect(SCREEN, RED, rect, 3)
    shown = ("*" * len(text)) if text else placeholder
    color = WHITE if text else GRAY
    txt = FONT.render(shown, True, color)
    SCREEN.blit(txt, (rect.x + 16, rect.y + rect.h // 2 - txt.get_height() // 2))


def ascii_input_char(ch, allow_space=True):
    if not ch:
        return ""
    if ord(ch) >= 128:
        return ""
    if ch in "\r\n\t":
        return ""
    if not allow_space and ch == " ":
        return ""
    return ch

def append_ascii(text, ch, limit, allow_space=True):
    ch = ascii_input_char(ch, allow_space=allow_space)
    if ch and len(text) < limit:
        return text + ch
    return text

def get_start(level):
    for o in level["objects"]:
        if o["type"] == "start":
            return o["x"], o["y"]
    return 100, 450


def reset_player_to_start(level):
    sx, sy = get_start(level)
    return Player(sx, sy)

def world_to_screen(x, y, cam):
    return int(x - cam.x), int(y - cam.y)

def screen_to_world(x, y, cam):
    return x + cam.x, y + cam.y

def cell_from_screen(pos, cam):
    wx, wy = screen_to_world(pos[0], pos[1], cam)
    return snap_floor(wx), snap_floor(wy)

def remove_cell(level, x, y):
    level["objects"] = [
        o for o in level["objects"]
        if not (o["x"] == x and o["y"] == y and o["type"] in ("block", "spike"))
    ]

def place_cell(level, tool, x, y):
    if tool == "erase":
        remove_cell(level, x, y)
        return

    if tool in ("block", "spike"):
        remove_cell(level, x, y)
        level["objects"].append({"type": tool, "x": x, "y": y})
        return

    if tool in ("start", "finish"):
        level["objects"] = [o for o in level["objects"] if o["type"] != tool]
        level["objects"].append({"type": tool, "x": x, "y": y})

def find_at(level, x, y):
    for i in range(len(level["objects"]) - 1, -1, -1):
        o = level["objects"][i]
        if o["x"] == x and o["y"] == y:
            return i
    return None

def draw_grid(cam):
    start_x = int(cam.x // GRID) * GRID
    end_x = int((cam.x + WIDTH) // GRID + 1) * GRID
    start_y = int(cam.y // GRID) * GRID
    end_y = int((cam.y + HEIGHT - PANEL_H) // GRID + 1) * GRID

    for x in range(start_x, end_x + GRID, GRID):
        sx = x - cam.x
        pygame.draw.line(SCREEN, (30, 30, 35), (sx, 0), (sx, HEIGHT - PANEL_H))

    for y in range(start_y, end_y + GRID, GRID):
        sy = y - cam.y
        pygame.draw.line(SCREEN, (30, 30, 35), (0, sy), (WIDTH, sy))

def draw_object(obj, cam, editor=False, selected=False):
    sr = pygame.Rect(obj["x"] - cam.x, obj["y"] - cam.y, GRID, GRID)
    t = obj["type"]

    if t == "block":
        pygame.draw.rect(SCREEN, GRAY, sr)
        pygame.draw.rect(SCREEN, BLACK, sr, 3)

    elif t == "spike":
        pygame.draw.rect(SCREEN, PINK, sr)
        pygame.draw.rect(SCREEN, BLACK, sr, 3)

    elif t == "finish":
        pygame.draw.rect(SCREEN, GREEN, sr)
        pygame.draw.rect(SCREEN, BLACK, sr, 3)

    elif t == "start":
        if editor:
            pygame.draw.rect(SCREEN, (35, 35, 42), sr)
            pygame.draw.rect(SCREEN, YELLOW, sr, 3)
            a = SMALL.render("start", True, YELLOW)
            b = SMALL.render("pos", True, YELLOW)
            SCREEN.blit(a, a.get_rect(center=(sr.centerx, sr.centery - 11)))
            SCREEN.blit(b, b.get_rect(center=(sr.centerx, sr.centery + 11)))

    if selected and editor:
        pygame.draw.rect(SCREEN, YELLOW, sr, 5)

def draw_world(level, cam, editor=False, selected=None, player=None):
    SCREEN.fill(DARK)
    if editor:
        draw_grid(cam)

    for i, obj in enumerate(level["objects"]):
        draw_object(obj, cam, editor, selected == i)

    if player:
        pr = pygame.Rect(player.rect.x - cam.x, player.rect.y - cam.y, player.rect.w, player.rect.h)
        pygame.draw.rect(SCREEN, PLAYER_RED, pr)
        pygame.draw.rect(SCREEN, BLACK, pr, 3)

class Player:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x + 5, y + 5, GRID - 10, GRID - 10)
        self.vel = pygame.Vector2(0, 0)
        self.speed = 7
        self.accel = 1.15
        self.friction = 0.78
        self.jump_power = -16
        self.gravity = 0.78
        self.on_ground = False

        self.left_down = False
        self.right_down = False
        self.jump_buffer = False

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_a, pygame.K_LEFT):
                self.left_down = True
            if event.key in (pygame.K_d, pygame.K_RIGHT):
                self.right_down = True
            if event.key in (pygame.K_w, pygame.K_UP, pygame.K_SPACE):
                self.jump_buffer = True

        if event.type == pygame.KEYUP:
            if event.key in (pygame.K_a, pygame.K_LEFT):
                self.left_down = False
            if event.key in (pygame.K_d, pygame.K_RIGHT):
                self.right_down = False

    def update(self, blocks):
        if self.left_down and not self.right_down:
            self.vel.x -= self.accel
        elif self.right_down and not self.left_down:
            self.vel.x += self.accel
        else:
            self.vel.x *= self.friction
            if abs(self.vel.x) < 0.08:
                self.vel.x = 0

        self.vel.x = clamp(self.vel.x, -self.speed, self.speed)

        if self.jump_buffer and self.on_ground:
            self.vel.y = self.jump_power
        self.jump_buffer = False

        self.vel.y += self.gravity
        self.vel.y = min(self.vel.y, 22)

        self.rect.x += int(round(self.vel.x))
        for b in blocks:
            if self.rect.colliderect(b):
                if self.vel.x > 0:
                    self.rect.right = b.left
                elif self.vel.x < 0:
                    self.rect.left = b.right
                self.vel.x = 0

        self.rect.y += int(round(self.vel.y))
        self.on_ground = False
        for b in blocks:
            if self.rect.colliderect(b):
                if self.vel.y > 0:
                    self.rect.bottom = b.top
                    self.vel.y = 0
                    self.on_ground = True
                elif self.vel.y < 0:
                    self.rect.top = b.bottom
                    self.vel.y = 0

def transition_to_game():
    fx = make_fx()
    start = time.time()

    while True:
        CLOCK.tick(FPS)
        elapsed = time.time() - start

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

        draw_fx_bg(fx)

        if elapsed >= 0.10:
            pygame.draw.line(SCREEN, RED, (WIDTH // 2, 0), (WIDTH // 2, HEIGHT), 10)
        if elapsed >= 0.32:
            pygame.draw.line(SCREEN, RED, (0, HEIGHT // 2), (WIDTH, HEIGHT // 2), 10)
        if elapsed >= 0.55:
            count = min(34, int((elapsed - 0.55) / 0.055))
            for i in range(count):
                pygame.draw.circle(SCREEN, RED, (WIDTH // 2, HEIGHT // 2), 30 + i * 42, 4)

        if random.random() < 0.45:
            txt = SMALL.render("BREAKCUBE LOADING", True, WHITE)
            SCREEN.blit(txt, txt.get_rect(center=(WIDTH // 2 + random.randint(-6, 6), HEIGHT // 2 + 75 + random.randint(-4, 4))))

        pygame.display.flip()

        if elapsed >= 5:
            return

def menu():
    fx = make_fx()
    play = Button("PLAY", (WIDTH // 2 - 160, 200, 320, 70))
    multiplayer = Button("MULTIPLAYER", (WIDTH // 2 - 160, 285, 320, 70))
    account = Button("ACCOUNT", (WIDTH // 2 - 160, 370, 320, 70))
    settings = Button("SETTINGS", (WIDTH // 2 - 160, 455, 320, 70))
    quit_btn = Button("QUIT", (WIDTH // 2 - 160, 540, 320, 70))

    msg = ""
    msg_time = 0

    while True:
        CLOCK.tick(FPS)
        draw_fx_bg(fx)

        pygame.draw.rect(SCREEN, RED, (0, 0, WIDTH, 10))
        pygame.draw.rect(SCREEN, RED, (0, HEIGHT - 10, WIDTH, 10))
        draw_title("BREAKCUBE", 105)

        acc = load_account()
        acc_text = "ACCOUNT: " + (acc["name"] if acc else "NOT REGISTERED")
        SCREEN.blit(SMALL.render(acc_text, True, GREEN if acc else PINK), (25, 28))

        for b in (play, multiplayer, account, settings, quit_btn):
            b.draw()

        if msg and time.time() - msg_time < 2.2:
            box = pygame.Rect(WIDTH // 2 - 310, 145, 620, 45)
            pygame.draw.rect(SCREEN, (18, 18, 25), box)
            pygame.draw.rect(SCREEN, RED, box, 3)
            t = SMALL.render(msg, True, WHITE)
            SCREEN.blit(t, t.get_rect(center=box.center))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if play.hit(event.pos):
                    transition_to_game()
                    game_loop()
                    fx = make_fx()
                elif multiplayer.hit(event.pos):
                    if load_account():
                        multiplayer_screen()
                        fx = make_fx()
                    else:
                        msg = "REGISTER ACCOUNT FIRST"
                        msg_time = time.time()
                elif account.hit(event.pos):
                    account_screen()
                    fx = make_fx()
                elif settings.hit(event.pos):
                    settings_screen()
                    fx = make_fx()
                elif quit_btn.hit(event.pos):
                    pygame.quit()
                    raise SystemExit

        pygame.display.flip()


def draw_loading_overlay(text="LOADING..."):
    fx = make_fx()
    start_time = time.time()

    while True:
        CLOCK.tick(FPS)
        draw_fx_bg(fx)

        box = pygame.Rect(WIDTH // 2 - 280, HEIGHT // 2 - 80, 560, 160)
        pygame.draw.rect(SCREEN, (10, 10, 15), box)
        pygame.draw.rect(SCREEN, RED, box, 4)

        title = BIG.render(text, True, WHITE)
        SCREEN.blit(title, title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 25)))

        dots = "." * (int((time.time() - start_time) * 4) % 4)
        sub = SMALL.render("PLEASE WAIT" + dots, True, GRAY)
        SCREEN.blit(sub, sub.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 45)))

        pygame.display.flip()
        yield

def udp_request_raw(packet, timeout=2.5, retries=3):
    """UDP JSON request with fallback.

    1) Tries SERVER_HOST/SERVER_PORT, usually playit.
    2) If that does not answer, tries 127.0.0.1:8484.
    This is important when the server is running locally, but the client still has playit host.
    """
    timeout = max(0.7, float(timeout))
    retries = max(1, int(retries))

    packet = dict(packet or {})
    packet.setdefault("request_id", "%08x%08x" % (
        random.randint(0, 0xFFFFFFFF),
        random.randint(0, 0xFFFFFFFF)
    ))

    raw = json.dumps(packet, ensure_ascii=False).encode("utf-8")
    last_error = "udp timeout"

    targets = [(SERVER_HOST, SERVER_PORT)]
    try:
        local_target = (LOCAL_SERVER_HOST, LOCAL_SERVER_PORT)
        if local_target not in targets:
            targets.append(local_target)
    except NameError:
        pass

    for host, port in targets:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)

            for attempt in range(retries):
                try:
                    sock.sendto(raw, (host, port))

                    deadline = time.time() + timeout
                    while time.time() < deadline:
                        try:
                            data, _ = sock.recvfrom(65535)
                        except socket.timeout:
                            last_error = f"udp timeout {host}:{port}"
                            break

                        try:
                            response = json.loads(data.decode("utf-8"))
                        except Exception as e:
                            last_error = "bad udp json: " + str(e)
                            continue

                        if response.get("request_id") and response.get("request_id") != packet.get("request_id"):
                            last_error = "old udp response"
                            continue

                        if not response.get("ok"):
                            print("SERVER ANSWER ERROR:", packet.get("path"), response.get("error"))
                        return response

                except OSError as e:
                    last_error = f"udp os error {host}:{port}: {e}"
                    time.sleep(0.08)
                except Exception as e:
                    last_error = f"udp error {host}:{port}: {e}"
                    time.sleep(0.08)

                time.sleep(0.08 + attempt * 0.03)

        finally:
            try:
                if sock:
                    sock.close()
            except Exception:
                pass

    print("UDP REQUEST FAILED:", packet.get("method"), packet.get("path"), last_error)
    return {"ok": False, "error": last_error}

def udp_request(packet, timeout=2.5, retries=3, loading_text="LOADING..."):
    result_box = {"done": False, "result": None}

    def worker():
        result_box["result"] = udp_request_raw(packet, timeout=timeout, retries=retries)
        result_box["done"] = True

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    loader = draw_loading_overlay(loading_text)

    started = time.time()
    max_wait = max(4.0, float(timeout) * max(1, int(retries)) * 2 + 1.0)

    while not result_box["done"]:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return {"ok": False, "error": "cancelled"}

        if time.time() - started > max_wait:
            return {"ok": False, "error": "client wait timeout"}

        next(loader)

    return result_box["result"] or {"ok": False, "error": "no response"}

def api_get(path, params=None, timeout=2.5):
    label = "LOADING..."
    if path == "/api/songs":
        label = "LOADING MUSIC..."
    elif path in ("/api/song_stream_start", "/api/song_stream_missing", "/api/song_info", "/api/song_chunk"):
        label = "DOWNLOADING..."
    elif path in ("/api/levels", "/api/level"):
        label = "LOADING LEVELS..."

    # Lists should fail fast instead of looking like infinite loading.
    retries = 2 if path in ("/api/levels", "/api/level") else 3

    return udp_request({
        "method": "GET",
        "path": path,
        "params": params or {}
    }, timeout=max(float(timeout), 1.5), retries=retries, loading_text=label)

def api_post(path, data, timeout=2.5):
    return udp_request({
        "method": "POST",
        "path": path,
        "data": data or {}
    }, timeout=max(float(timeout), 2.0), retries=3, loading_text="SAVING...")

def get_account_name():
    acc = load_account()
    return acc["name"] if acc else None

def get_account_token():
    acc = load_account()
    return acc["token"] if acc else ""

def account_screen():
    fx = make_fx()
    acc = load_account()
    username = acc["name"] if acc else ""
    password = ""
    active = "user"
    message = "REGISTER OR LOGIN"

    user_rect = pygame.Rect(WIDTH // 2 - 300, 240, 600, 65)
    pass_rect = pygame.Rect(WIDTH // 2 - 300, 325, 600, 65)

    login = Button("LOGIN", (WIDTH // 2 - 310, 430, 200, 70))
    register = Button("REGISTER", (WIDTH // 2 - 80, 430, 240, 70))
    logout = Button("LOGOUT", (WIDTH // 2 + 190, 430, 210, 70))
    back = Button("BACK", (WIDTH // 2 - 140, 525, 280, 70))

    while True:
        CLOCK.tick(FPS)
        draw_fx_bg(fx)
        draw_title("ACCOUNT", 120)

        cur = load_account()
        if cur:
            t = SMALL.render("LOGGED AS: " + cur["name"], True, GREEN)
            SCREEN.blit(t, t.get_rect(center=(WIDTH // 2, 190)))
        else:
            t = SMALL.render(message, True, YELLOW)
            SCREEN.blit(t, t.get_rect(center=(WIDTH // 2, 190)))

        draw_input(user_rect, username, "nickname...")
        draw_password_input(pass_rect, password, "password...")

        login.draw()
        register.draw()
        logout.draw()
        back.draw()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                if event.key == pygame.K_TAB:
                    active = "pass" if active == "user" else "user"
                elif event.key == pygame.K_BACKSPACE:
                    if active == "user":
                        username = username[:-1]
                    else:
                        password = password[:-1]
                elif event.key == pygame.K_RETURN:
                    res = api_post("/api/user/login", {"username": username, "password": password}, timeout=2)
                    if res.get("ok"):
                        save_account(res["username"], res["token"])
                        message = "LOGGED IN"
                    else:
                        message = res.get("error", "LOGIN ERROR").upper()
                else:
                    ch = event.unicode
                    if ch:
                        if active == "user" and len(username) < 18 and (ch.isalnum() or ch in "_-."):
                            username = append_ascii(username, ch, 18, allow_space=False)
                        elif active == "pass" and len(password) < 32:
                            password = append_ascii(password, ch, 32, allow_space=True)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if user_rect.collidepoint(event.pos):
                    active = "user"
                elif pass_rect.collidepoint(event.pos):
                    active = "pass"
                elif back.hit(event.pos):
                    return
                elif logout.hit(event.pos):
                    clear_account()
                    message = "LOGGED OUT"
                elif login.hit(event.pos):
                    res = api_post("/api/user/login", {"username": username, "password": password}, timeout=2)
                    if res.get("ok"):
                        save_account(res["username"], res["token"])
                        message = "LOGGED IN"
                    else:
                        message = res.get("error", "LOGIN ERROR").upper()
                elif register.hit(event.pos):
                    res = api_post("/api/user/register", {"username": username, "password": password}, timeout=2)
                    if res.get("ok"):
                        save_account(res["username"], res["token"])
                        message = "REGISTERED"
                    else:
                        message = res.get("error", "REGISTER ERROR").upper()

        pygame.display.flip()



def prompt_text_screen(title_text, placeholder, initial=""):
    fx = make_fx()
    text = initial
    back = Button("BACK", (WIDTH // 2 - 240, 440, 210, 70))
    ok = Button("OK", (WIDTH // 2 + 30, 440, 250, 70))
    input_rect = pygame.Rect(WIDTH // 2 - 300, 285, 600, 70)

    while True:
        CLOCK.tick(FPS)
        draw_fx_bg(fx)
        draw_title(title_text, 135)
        draw_input(input_rect, text, placeholder)
        back.draw()
        ok.draw()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                if event.key == pygame.K_RETURN:
                    return text.strip() if text.strip() else None
                if event.key == pygame.K_BACKSPACE:
                    text = text[:-1]
                else:
                    ch = event.unicode
                    if ch and len(text) < 40:
                        text = append_ascii(text, ch, 40, allow_space=True)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back.hit(event.pos):
                    return None
                if ok.hit(event.pos):
                    return text.strip() if text.strip() else None

        pygame.display.flip()

def level_from_server_data(data):
    return normalize_level({
        "name": data.get("name", "Online Level"),
        "objects": data.get("objects", []),
        "song": data.get("song", "")
    })

def draw_download_progress(song_name, done, total, status=""):
    SCREEN.fill(BLACK)

    box = pygame.Rect(WIDTH // 2 - 360, HEIGHT // 2 - 120, 720, 240)
    pygame.draw.rect(SCREEN, (10, 10, 15), box)
    pygame.draw.rect(SCREEN, RED, box, 4)

    title = BIG.render("DOWNLOADING", True, WHITE)
    SCREEN.blit(title, title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 70)))

    name_txt = SMALL.render(song_name, True, GRAY)
    SCREEN.blit(name_txt, name_txt.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 25)))

    bar = pygame.Rect(WIDTH // 2 - 280, HEIGHT // 2 + 20, 560, 34)
    pygame.draw.rect(SCREEN, (25, 25, 30), bar)
    pygame.draw.rect(SCREEN, GRAY, bar, 2)

    total = max(1, int(total))
    done = max(0, min(int(done), total))
    fill_w = int(bar.w * done / total)
    pygame.draw.rect(SCREEN, RED, (bar.x, bar.y, fill_w, bar.h))

    percent = int(done * 100 / total)
    ptxt = SMALL.render(f"{percent}%  {done}/{total}", True, WHITE)
    SCREEN.blit(ptxt, ptxt.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 78)))

    if status:
        stxt = SMALL.render(status, True, YELLOW)
        SCREEN.blit(stxt, stxt.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 108)))

    pygame.display.flip()

def download_song(name):
    if not name:
        return None

    SONG_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    safe = os.path.basename(str(name))
    target = SONG_CACHE_DIR / safe

    if target.exists() and target.stat().st_size > 0:
        return str(target)

    session = ("%08x" % random.randint(0, 0xFFFFFFFF)).encode("ascii")
    tmp = SONG_CACHE_DIR / (safe + ".part")

    try:
        if tmp.exists():
            tmp.unlink()
    except Exception:
        pass

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)

    def send_json(packet):
        raw = json.dumps(packet, ensure_ascii=False).encode("utf-8")
        sock.sendto(raw, (SERVER_HOST, SERVER_PORT))

    start_packet = {
        "method": "GET",
        "path": "/api/song_stream_start",
        "params": {"name": safe, "session": session.decode("ascii")}
    }
    send_json(start_packet)

    info = None
    start_wait = time.time()
    last_start_request = start_wait

    while time.time() - start_wait < 10:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sock.close()
                pygame.quit()
                raise SystemExit

        if time.time() - last_start_request > 1.0:
            send_json(start_packet)
            last_start_request = time.time()

        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            continue

        if data.startswith(b"BCSG"):
            continue

        try:
            info = json.loads(data.decode("utf-8"))
            if info.get("ok"):
                break
        except Exception:
            pass

    if not info or not info.get("ok"):
        sock.close()
        return None

    total_size = int(info.get("size", 0))
    chunks = int(info.get("chunks", 0))

    if total_size <= 0 or chunks <= 0:
        sock.close()
        return None

    results = [None] * chunks
    got = 0
    last_missing_request = 0
    last_packet_time = time.time()
    global_deadline = time.time() + 240

    while got < chunks and time.time() < global_deadline:
        CLOCK.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sock.close()
                pygame.quit()
                raise SystemExit

        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            data = None

        if data and data.startswith(b"BCSG") and len(data) >= 16:
            pkt_session = data[4:12]
            if pkt_session == session:
                idx = struct.unpack("!I", data[12:16])[0]
                if 0 <= idx < chunks and results[idx] is None:
                    results[idx] = data[16:]
                    got += 1
                    last_packet_time = time.time()

        now = time.time()
        if now - last_missing_request > 0.35 and got < chunks:
            missing = [i for i, chunk in enumerate(results) if chunk is None]
            send_json({
                "method": "GET",
                "path": "/api/song_stream_missing",
                "params": {
                    "name": safe,
                    "session": session.decode("ascii"),
                    "indices": missing[:80]
                }
            })
            last_missing_request = now

        status = "STREAMING UDP"
        if time.time() - last_packet_time > 3:
            status = "REPAIRING UDP PACKETS"

        draw_download_progress(safe, got, chunks, status)

    sock.close()

    if got < chunks:
        draw_download_progress(safe, got, chunks, "NETWORK TOO SLOW")
        pygame.time.delay(500)
        return None

    try:
        with open(tmp, "wb") as f:
            for raw in results:
                if raw is None:
                    return None
                f.write(raw)

        if tmp.stat().st_size != total_size:
            try:
                tmp.unlink()
            except Exception:
                pass
            return None

        tmp.replace(target)
        draw_download_progress(safe, chunks, chunks, "SAVED")
        pygame.time.delay(250)
        return str(target)

    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return None

MUSIC_VOLUME = load_settings().get("volume", 0.7)

def set_music_volume(value):
    global MUSIC_VOLUME
    MUSIC_VOLUME = clamp(float(value), 0.0, 1.0)
    save_settings({"volume": MUSIC_VOLUME})
    try:
        pygame.mixer.music.set_volume(MUSIC_VOLUME)
    except Exception:
        pass

def play_song_file(path):
    if not path:
        return
    try:
        pygame.mixer.music.stop()
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(MUSIC_VOLUME)
        pygame.mixer.music.play()
    except Exception:
        pass

def stop_music():
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass


def multiplayer_screen():
    fx = make_fx()
    account = get_account_name()
    if not account:
        return

    search = Button("SEARCH", (WIDTH // 2 - 170, 190, 340, 65))
    editor = Button("EDITOR", (WIDTH // 2 - 170, 275, 340, 65))
    my_levels = Button("MY LEVELS", (WIDTH // 2 - 170, 360, 340, 65))
    popular = Button("POPULAR", (WIDTH // 2 - 170, 445, 340, 65))
    back = Button("BACK", (WIDTH // 2 - 170, 530, 340, 65))

    while True:
        CLOCK.tick(FPS)
        draw_fx_bg(fx)
        draw_title("MULTIPLAYER", 95)
        SCREEN.blit(SMALL.render("Logged as: " + account, True, GREEN), (35, 35))

        for b in (search, editor, my_levels, popular, back):
            b.draw()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back.hit(event.pos):
                    return
                if editor.hit(event.pos):
                    name = prompt_text_screen("LEVEL NAME", "enter level name...")
                    if name:
                        lvl = default_level()
                        lvl["name"] = name
                        lvl["song"] = ""
                        online_level_editor(lvl, None)
                        fx = make_fx()
                if my_levels.hit(event.pos):
                    my_levels_screen(account)
                    fx = make_fx()
                if popular.hit(event.pos):
                    online_levels_list_screen(account, mode="popular")
                    fx = make_fx()
                if search.hit(event.pos):
                    online_search_screen(account)
                    fx = make_fx()
        pygame.display.flip()

def online_search_screen(account):
    fx = make_fx()
    query = ""
    input_rect = pygame.Rect(WIDTH // 2 - 330, 175, 660, 65)
    back = Button("BACK", (40, HEIGHT - 95, 150, 60))
    refresh = Button("REFRESH", (WIDTH - 220, HEIGHT - 95, 180, 60))

    all_items = []
    message = "LOADING..."
    loading = True
    last_load = 0

    def load_once():
        res = api_get("/api/levels", {"page": 1, "per_page": 100}, timeout=2)
        if res.get("ok"):
            return res.get("levels", []), ""
        return [], "SERVER ERROR"

    all_items, message = load_once()
    loading = False

    while True:
        CLOCK.tick(FPS)
        draw_fx_bg(fx)
        draw_title("SEARCH", 90)
        draw_input(input_rect, query, "search level name...")
        back.draw()
        refresh.draw()

        q = query.lower().strip()
        items = [x for x in all_items if q in x.get("name", "").lower()] if q else all_items
        draw_level_rows(items[:7], WIDTH // 2 - 390, 280, account)

        if message:
            t = SMALL.render(message, True, YELLOW)
            SCREEN.blit(t, t.get_rect(center=(WIDTH // 2, 255)))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                if event.key == pygame.K_BACKSPACE:
                    query = query[:-1]
                else:
                    ch = event.unicode
                    if ch and len(query) < 32:
                        query = append_ascii(query, ch, 32, allow_space=True)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back.hit(event.pos):
                    return
                if refresh.hit(event.pos):
                    all_items, message = load_once()
                clicked = row_clicked(items[:7], WIDTH // 2 - 390, 280, event.pos)
                if clicked:
                    level_detail_screen(clicked.get("id"), account)
                    fx = make_fx()

        pygame.display.flip()

def online_levels_list_screen(account, mode="popular"):
    fx = make_fx()
    page = 1
    back = Button("BACK", (40, HEIGHT - 95, 150, 60))
    prev_btn = Button("PREV", (WIDTH // 2 - 260, HEIGHT - 95, 170, 60))
    next_btn = Button("NEXT", (WIDTH // 2 + 90, HEIGHT - 95, 170, 60))
    refresh = Button("REFRESH", (WIDTH - 220, HEIGHT - 95, 180, 60))

    items = []
    pages = 1
    message = ""

    def load_page(p):
        res = api_get("/api/levels", {"page": p, "per_page": 5, "order": "popular"}, timeout=2)
        if not res.get("ok"):
            return [], 1, ("SERVER ERROR: " + str(res.get("error", "unknown"))[:60])
        arr = res.get("levels", [])
        arr = sorted(arr, key=lambda x: int(x.get("likes", 0)) - int(x.get("dislikes", 0)), reverse=True)
        return arr, max(1, int(res.get("pages", 1))), ""

    items, pages, message = load_page(page)

    while True:
        CLOCK.tick(FPS)
        draw_fx_bg(fx)
        draw_title("POPULAR", 90)

        draw_level_rows(items, WIDTH // 2 - 390, 210, account)
        SCREEN.blit(SMALL.render(f"PAGE {page}/{pages}", True, WHITE), (WIDTH // 2 - 60, HEIGHT - 115))
        if message:
            t = SMALL.render(message, True, YELLOW)
            SCREEN.blit(t, t.get_rect(center=(WIDTH // 2, 165)))

        back.draw()
        prev_btn.draw()
        next_btn.draw()
        refresh.draw()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back.hit(event.pos):
                    return
                if refresh.hit(event.pos):
                    items, pages, message = load_page(page)
                if prev_btn.hit(event.pos):
                    page = max(1, page - 1)
                    items, pages, message = load_page(page)
                if next_btn.hit(event.pos):
                    page = min(pages + 1, page + 1)
                    items, pages, message = load_page(page)
                clicked = row_clicked(items, WIDTH // 2 - 390, 210, event.pos)
                if clicked:
                    level_detail_screen(clicked.get("id"), account)
                    items, pages, message = load_page(page)
                    fx = make_fx()

        pygame.display.flip()

def my_levels_screen(account):
    fx = make_fx()
    page = 1
    back = Button("BACK", (40, HEIGHT - 95, 150, 60))
    prev_btn = Button("PREV", (WIDTH // 2 - 260, HEIGHT - 95, 170, 60))
    next_btn = Button("NEXT", (WIDTH // 2 + 90, HEIGHT - 95, 170, 60))
    refresh = Button("REFRESH", (WIDTH - 220, HEIGHT - 95, 180, 60))

    items = []
    pages = 1
    message = ""

    def load_page(p):
        res = api_get("/api/levels", {"author": account, "page": p, "per_page": 5}, timeout=2)
        if not res.get("ok"):
            return [], 1, ("SERVER ERROR: " + str(res.get("error", "unknown"))[:60])
        return res.get("levels", []), max(1, int(res.get("pages", 1))), ""

    items, pages, message = load_page(page)

    while True:
        CLOCK.tick(FPS)
        draw_fx_bg(fx)
        draw_title("MY LEVELS", 90)

        draw_level_rows(items, WIDTH // 2 - 390, 210, account)
        SCREEN.blit(SMALL.render(f"PAGE {page}/{pages}", True, WHITE), (WIDTH // 2 - 60, HEIGHT - 115))
        if message:
            t = SMALL.render(message, True, YELLOW)
            SCREEN.blit(t, t.get_rect(center=(WIDTH // 2, 165)))

        back.draw()
        prev_btn.draw()
        next_btn.draw()
        refresh.draw()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back.hit(event.pos):
                    return
                if refresh.hit(event.pos):
                    items, pages, message = load_page(page)
                if prev_btn.hit(event.pos):
                    page = max(1, page - 1)
                    items, pages, message = load_page(page)
                if next_btn.hit(event.pos):
                    page = min(pages + 1, page + 1)
                    items, pages, message = load_page(page)
                clicked = row_clicked(items, WIDTH // 2 - 390, 210, event.pos)
                if clicked:
                    level_detail_screen(clicked.get("id"), account)
                    items, pages, message = load_page(page)
                    fx = make_fx()

        pygame.display.flip()

def draw_level_rows(items, x, y, account):
    w = 780
    for i, lvl in enumerate(items):
        r = pygame.Rect(x, y + i * 78, w, 62)
        pygame.draw.rect(SCREEN, (22, 22, 28), r)
        pygame.draw.rect(SCREEN, GRAY, r, 2)
        name = SMALL.render(lvl.get("name", "Untitled"), True, WHITE)
        status = "PUBLIC" if lvl.get("published") else "DRAFT"
        meta = SMALL.render(f"ID {lvl.get('id','?')} | {status} | by {lvl.get('author','?')} | likes {lvl.get('likes',0)} | dislikes {lvl.get('dislikes',0)}", True, GRAY)
        SCREEN.blit(name, (r.x + 15, r.y + 7))
        SCREEN.blit(meta, (r.x + 15, r.y + 34))

def row_clicked(items, x, y, pos):
    w = 780
    for i, lvl in enumerate(items):
        r = pygame.Rect(x, y + i * 78, w, 62)
        if r.collidepoint(pos):
            return lvl
    return None

def level_detail_screen(level_id, account):
    fx = make_fx()
    comment_text = ""
    comment_page = 0
    confirm_delete = False

    play_btn = Button("PLAY LEVEL", (WIDTH // 2 - 330, 190, 260, 65))
    edit_btn = Button("EDITOR", (WIDTH // 2 - 30, 190, 220, 65))
    like_btn = Button("LIKE", (WIDTH // 2 + 230, 190, 150, 65))
    dislike_btn = Button("DISLIKE", (WIDTH // 2 + 400, 190, 180, 65))
    delete_btn = Button("DELETE LEVEL", (WIDTH - 310, 270, 260, 60))
    yes_btn = Button("YES DELETE", (WIDTH - 330, 340, 280, 60))
    no_btn = Button("CANCEL", (WIDTH - 330, 410, 280, 60))
    send_btn = Button("SEND", (WIDTH // 2 + 270, HEIGHT - 150, 150, 60))
    prev_comments = Button("COMMENTS < ", (WIDTH // 2 - 390, HEIGHT - 215, 220, 55))
    next_comments = Button("COMMENTS > ", (WIDTH // 2 + 170, HEIGHT - 215, 220, 55))
    back = Button("BACK", (40, HEIGHT - 95, 150, 60))
    refresh = Button("REFRESH", (WIDTH - 220, HEIGHT - 95, 180, 60))
    input_rect = pygame.Rect(WIDTH // 2 - 390, HEIGHT - 150, 640, 60)

    lvl = None
    comments = []
    message = ""

    def load_detail():
        res = api_get("/api/level", {"id": level_id}, timeout=2)
        if res.get("ok"):
            return res["level"], res.get("comments", []), ""
        return None, [], "SERVER ERROR"

    lvl, comments, message = load_detail()

    while True:
        CLOCK.tick(FPS)
        draw_fx_bg(fx)

        if not lvl:
            draw_title("NOT FOUND", 120)
            if message:
                t = SMALL.render(message, True, YELLOW)
                SCREEN.blit(t, t.get_rect(center=(WIDTH // 2, 220)))
            back.draw()
            refresh.draw()

            pygame.display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    raise SystemExit
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if back.hit(event.pos):
                        return
                    if refresh.hit(event.pos):
                        lvl, comments, message = load_detail()
            continue

        is_owner = lvl.get("author") == account

        draw_title(lvl.get("name", "LEVEL"), 95)

        play_btn.draw()
        if is_owner:
            edit_btn.draw()
            delete_btn.draw()
            if confirm_delete:
                yes_btn.draw()
                no_btn.draw()

        like_btn.draw()
        dislike_btn.draw()
        back.draw()
        refresh.draw()

        status = "PUBLIC" if lvl.get("published") else "DRAFT"
        info = SMALL.render(f"ID {lvl.get('id','?')} | {status} | by {lvl.get('author','?')} | likes {lvl.get('likes',0)} | dislikes {lvl.get('dislikes',0)}", True, WHITE)
        SCREEN.blit(info, info.get_rect(center=(WIDTH // 2, 155)))

        song = lvl.get("song", "") or "none"
        song_txt = SMALL.render("MUSIC: " + song, True, GREEN if song != "none" else GRAY)
        SCREEN.blit(song_txt, song_txt.get_rect(center=(WIDTH // 2, HEIGHT - 45)))

        per_page = 5
        max_page = max(0, (len(comments) - 1) // per_page)
        comment_page = max(0, min(comment_page, max_page))
        start_i = comment_page * per_page
        visible_comments = comments[start_i:start_i + per_page]

        cy = 295
        for c in visible_comments:
            box = pygame.Rect(WIDTH // 2 - 390, cy, 780, 52)
            pygame.draw.rect(SCREEN, (22, 22, 28), box)
            pygame.draw.rect(SCREEN, GRAY, box, 2)
            txt = SMALL.render(f"{c.get('author','anon')}: {c.get('text','')}", True, WHITE)
            SCREEN.blit(txt, (box.x + 12, box.y + 12))
            cy += 62

        prev_comments.draw()
        next_comments.draw()
        page_txt = SMALL.render(f"{comment_page + 1}/{max_page + 1}", True, WHITE)
        SCREEN.blit(page_txt, page_txt.get_rect(center=(WIDTH // 2, HEIGHT - 188)))

        draw_input(input_rect, comment_text, "leave comment...")
        send_btn.draw()

        if message:
            t = SMALL.render(message, True, YELLOW)
            SCREEN.blit(t, t.get_rect(center=(WIDTH // 2, 260)))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                if event.key == pygame.K_BACKSPACE:
                    comment_text = comment_text[:-1]
                elif event.key == pygame.K_RETURN:
                    if comment_text.strip():
                        api_post("/api/level/comment", {"id": level_id, "author": account, "token": get_account_token(), "text": comment_text}, timeout=2)
                        comment_text = ""
                        lvl, comments, message = load_detail()
                        comment_page = max(0, (len(comments) - 1) // per_page)
                else:
                    ch = event.unicode
                    if ch:
                        comment_text = append_ascii(comment_text, ch, 120, allow_space=True)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back.hit(event.pos):
                    return
                if refresh.hit(event.pos):
                    lvl, comments, message = load_detail()

                if prev_comments.hit(event.pos):
                    comment_page = max(0, comment_page - 1)
                if next_comments.hit(event.pos):
                    comment_page = min(max_page, comment_page + 1)

                if play_btn.hit(event.pos):
                    play_online_level(lvl)
                    fx = make_fx()

                if is_owner and edit_btn.hit(event.pos):
                    online_level_editor(level_from_server_data(lvl), lvl)
                    lvl, comments, message = load_detail()
                    fx = make_fx()

                if is_owner and delete_btn.hit(event.pos):
                    confirm_delete = True

                if is_owner and confirm_delete and no_btn.hit(event.pos):
                    confirm_delete = False

                if is_owner and confirm_delete and yes_btn.hit(event.pos):
                    res = api_post("/api/level/unpublish", {"id": level_id, "token": get_account_token()}, timeout=2)
                    if res.get("ok"):
                        lvl = res["level"]
                        message = "REMOVED FROM PUBLIC LISTS"
                        confirm_delete = False
                    else:
                        message = res.get("error", "DELETE ERROR").upper()

                if like_btn.hit(event.pos):
                    api_post("/api/level/rate", {"id": level_id, "value": "like"}, timeout=2)
                    lvl, comments, message = load_detail()

                if dislike_btn.hit(event.pos):
                    api_post("/api/level/rate", {"id": level_id, "value": "dislike"}, timeout=2)
                    lvl, comments, message = load_detail()

                if send_btn.hit(event.pos) and comment_text.strip():
                    api_post("/api/level/comment", {"id": level_id, "author": account, "token": get_account_token(), "text": comment_text}, timeout=2)
                    comment_text = ""
                    lvl, comments, message = load_detail()
                    comment_page = max(0, (len(comments) - 1) // per_page)

        pygame.display.flip()

def play_online_level(server_level):
    lvl = level_from_server_data(server_level)
    song = server_level.get("song", "")
    if song:
        path = download_song(song)
        play_song_file(path)
    game_loop(level_override=lvl)
    stop_music()


def song_picker_screen(current_song=""):
    fx = make_fx()
    selected = current_song
    message = "LOADING..."
    back = Button("BACK", (40, HEIGHT - 95, 150, 60))
    set_btn = Button("SET TRACK", (WIDTH // 2 - 160, HEIGHT - 95, 320, 60))
    refresh = Button("REFRESH", (WIDTH - 220, HEIGHT - 95, 180, 60))

    def refresh_songs():
        SONG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        res = api_get("/api/songs", timeout=2)
        if res.get("ok"):
            return res.get("songs", []), ""
        return [], "SERVER ERROR"

    songs, message = refresh_songs()

    while True:
        CLOCK.tick(FPS)
        draw_fx_bg(fx)
        draw_title("MUSIC", 90)

        back.draw()
        set_btn.draw()
        refresh.draw()

        row_buttons = []
        y = 190

        for i, s in enumerate(songs[:8]):
            name = s.get("name", "")
            safe = os.path.basename(name)
            local_path = SONG_CACHE_DIR / safe
            local_ready = local_path.exists() and local_path.stat().st_size > 0
            status = "LOCAL" if local_ready else "SERVER"

            row = pygame.Rect(WIDTH // 2 - 460, y + i * 65, 920, 55)
            pygame.draw.rect(SCREEN, (22, 22, 28), row)
            pygame.draw.rect(SCREEN, GREEN if selected == name else GRAY, row, 3 if selected == name else 2)

            SCREEN.blit(SMALL.render(name, True, WHITE), (row.x + 15, row.y + 7))
            SCREEN.blit(SMALL.render(status, True, GREEN if local_ready else YELLOW), (row.x + 15, row.y + 30))

            dl_text = "READY" if local_ready else "DOWNLOAD"
            dl = Button(dl_text, (row.right - 335, row.y + 7, 165, 42), ("download", name))
            listen = Button("LISTEN", (row.right - 155, row.y + 7, 130, 42), ("listen", name))
            dl.draw()
            listen.draw()
            row_buttons.append((row, dl, listen, name))

        if not songs and not message:
            message = "NO SONGS FOUND"

        if message:
            t = SMALL.render(message, True, YELLOW)
            SCREEN.blit(t, t.get_rect(center=(WIDTH // 2, 155)))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    stop_music()
                    return current_song

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back.hit(event.pos):
                    stop_music()
                    return current_song

                if refresh.hit(event.pos):
                    songs, message = refresh_songs()

                if set_btn.hit(event.pos):
                    if selected:
                        p = download_song(selected)
                        if p:
                            stop_music()
                            return selected
                        message = "DOWNLOAD ERROR"
                    else:
                        message = "SELECT TRACK"

                for row, dl, listen, name in row_buttons:
                    # клик по строке просто выбирает трек
                    if row.collidepoint(event.pos) and not dl.hit(event.pos) and not listen.hit(event.pos):
                        selected = name
                        message = "SELECTED"

                    if dl.hit(event.pos):
                        selected = name
                        p = download_song(name)
                        message = "READY" if p else "DOWNLOAD ERROR"

                    if listen.hit(event.pos):
                        selected = name
                        p = download_song(name)
                        if p:
                            play_song_file(p)
                            message = "PLAYING"
                        else:
                            message = "DOWNLOAD ERROR"

        pygame.display.flip()


def online_level_editor(level, server_level=None):
    account = get_account_name()
    if not account:
        return
    level = normalize_level(level)
    server_id = server_level.get("id") if server_level else None
    current_published = bool(server_level.get("published", False)) if server_level else False
    if server_level:
        level["song"] = server_level.get("song", "")

    cam = pygame.Vector2(0, 0)
    selected_tool = "block"
    selected_index = None
    painting = False
    panning = False
    pan_start_mouse = pygame.Vector2(0, 0)
    pan_start_cam = pygame.Vector2(0, 0)
    last_painted = None
    message = ""

    buttons = [
        Button("BLOCK", (20, HEIGHT - PANEL_H + 30, 125, 60), "block"),
        Button("SPIKE", (155, HEIGHT - PANEL_H + 30, 125, 60), "spike"),
        Button("FINISH", (290, HEIGHT - PANEL_H + 30, 125, 60), "finish"),
        Button("START", (425, HEIGHT - PANEL_H + 30, 125, 60), "start"),
        Button("ERASE", (560, HEIGHT - PANEL_H + 30, 125, 60), "erase"),
        Button("MUSIC", (700, HEIGHT - PANEL_H + 30, 125, 60), "music"),
        Button("SAVE", (WIDTH - 620, HEIGHT - PANEL_H + 30, 130, 60), "save"),
        Button("PUBLISH", (WIDTH - 470, HEIGHT - PANEL_H + 30, 130, 60), "publish"),
        Button("PLAY", (WIDTH - 320, HEIGHT - PANEL_H + 30, 130, 60), "play"),
        Button("BACK", (WIDTH - 170, HEIGHT - PANEL_H + 30, 130, 60), "back"),
    ]

    while True:
        CLOCK.tick(FPS)
        draw_world(level, cam, editor=True, selected=selected_index)

        mx, my = pygame.mouse.get_pos()
        if my < HEIGHT - PANEL_H:
            gx, gy = cell_from_screen((mx, my), cam)
            preview = pygame.Rect(gx - cam.x, gy - cam.y, GRID, GRID)
            color = {"block": GRAY, "spike": PINK, "finish": GREEN, "start": YELLOW, "erase": RED}.get(selected_tool, WHITE)
            pygame.draw.rect(SCREEN, color, preview, 4)

        pygame.draw.rect(SCREEN, (12, 12, 15), (0, HEIGHT - PANEL_H, WIDTH, PANEL_H))
        pygame.draw.rect(SCREEN, RED, (0, HEIGHT - PANEL_H, WIDTH, 4))

        for b in buttons:
            b.draw(selected_tool == b.action)

        status = "PUBLIC" if current_published else "DRAFT"
        title = SMALL.render(level.get("name", "Untitled") + " | " + status + " | music: " + (level.get("song", "") or "none"), True, WHITE)
        SCREEN.blit(title, (20, HEIGHT - PANEL_H - 35))
        if message:
            SCREEN.blit(SMALL.render(message, True, YELLOW), (WIDTH - 420, HEIGHT - PANEL_H - 35))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked_button = False
                for b in buttons:
                    if b.hit(event.pos):
                        clicked_button = True
                        if b.action in ("block", "spike", "finish", "start", "erase"):
                            selected_tool = b.action
                        elif b.action == "music":
                            level["song"] = song_picker_screen(level.get("song", ""))
                        elif b.action == "save":
                            payload = {
                                "id": server_id,
                                "author": account,
                                "token": get_account_token(),
                                "name": level.get("name", "Untitled"),
                                "objects": level.get("objects", []),
                                "song": level.get("song", ""),
                                "published": current_published
                            }
                            res = api_post("/api/level/save", payload)
                            if res.get("ok"):
                                server_id = res["level"]["id"]
                                current_published = bool(res["level"].get("published", current_published))
                                message = "SAVED ONLINE"
                            else:
                                message = "SAVE ERROR"
                        elif b.action == "publish":
                            payload = {
                                "id": server_id,
                                "author": account,
                                "token": get_account_token(),
                                "name": level.get("name", "Untitled"),
                                "objects": level.get("objects", []),
                                "song": level.get("song", ""),
                                "published": True
                            }
                            res = api_post("/api/level/save", payload)
                            if res.get("ok"):
                                server_id = res["level"]["id"]
                                current_published = True
                                message = "PUBLISHED"
                            else:
                                message = "PUBLISH ERROR"
                        elif b.action == "play":
                            song = level.get("song", "")
                            if song:
                                play_song_file(download_song(song))
                            game_loop(level_override=level)
                            stop_music()
                        elif b.action == "back":
                            return
                        break

                if clicked_button or event.pos[1] >= HEIGHT - PANEL_H:
                    continue

                gx, gy = cell_from_screen(event.pos, cam)

                if selected_tool in DRAW_TOOLS:
                    painting = True
                    last_painted = None
                    place_cell(level, selected_tool, gx, gy)
                    selected_index = find_at(level, gx, gy)
                    last_painted = (gx, gy)
                else:
                    place_cell(level, selected_tool, gx, gy)
                    selected_index = find_at(level, gx, gy)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                panning = True
                pan_start_mouse = pygame.Vector2(event.pos)
                pan_start_cam = pygame.Vector2(cam)

            if event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    painting = False
                    last_painted = None
                if event.button == 3:
                    panning = False

            if event.type == pygame.MOUSEMOTION:
                if painting and event.pos[1] < HEIGHT - PANEL_H:
                    gx, gy = cell_from_screen(event.pos, cam)
                    if (gx, gy) != last_painted:
                        place_cell(level, selected_tool, gx, gy)
                        selected_index = find_at(level, gx, gy)
                        last_painted = (gx, gy)

                if panning:
                    mouse = pygame.Vector2(event.pos)
                    delta = mouse - pan_start_mouse
                    cam = pan_start_cam - delta

        pygame.display.flip()


def settings_screen():
    fx = make_fx()
    back = Button("BACK", (WIDTH // 2 - 150, 520, 300, 70))
    vol_down = Button("VOLUME -", (WIDTH // 2 - 360, 380, 240, 70))
    vol_up = Button("VOLUME +", (WIDTH // 2 + 120, 380, 240, 70))

    while True:
        CLOCK.tick(FPS)
        draw_fx_bg(fx)
        draw_title("SETTINGS", 145)

        box = pygame.Rect(WIDTH // 2 - 380, 260, 760, 190)
        pygame.draw.rect(SCREEN, DARK2, box)
        pygame.draw.rect(SCREEN, RED, box, 4)

        t = BIG.render(f"VOLUME {int(MUSIC_VOLUME * 100)}%", True, WHITE)
        SCREEN.blit(t, t.get_rect(center=(WIDTH // 2, 320)))

        bar = pygame.Rect(WIDTH // 2 - 260, 345, 520, 26)
        pygame.draw.rect(SCREEN, (25, 25, 30), bar)
        pygame.draw.rect(SCREEN, GRAY, bar, 2)
        pygame.draw.rect(SCREEN, RED, (bar.x, bar.y, int(bar.w * MUSIC_VOLUME), bar.h))

        vol_down.draw()
        vol_up.draw()
        back.draw()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if back.hit(event.pos):
                    return
                if vol_down.hit(event.pos):
                    set_music_volume(MUSIC_VOLUME - 0.1)
                if vol_up.hit(event.pos):
                    set_music_volume(MUSIC_VOLUME + 0.1)

        pygame.display.flip()

def game_pause_menu():
    music_was_playing = False
    try:
        music_was_playing = pygame.mixer.music.get_busy()
        if music_was_playing:
            pygame.mixer.music.pause()
    except Exception:
        pass

    continue_btn = Button("CONTINUE", (WIDTH // 2 - 170, HEIGHT // 2 - 55, 340, 80))
    quit_btn = Button("QUIT", (WIDTH // 2 - 170, HEIGHT // 2 + 50, 340, 80))

    confirm = False
    yes_btn = Button("YES", (WIDTH // 2 - 220, HEIGHT // 2 + 70, 190, 70))
    no_btn = Button("NO", (WIDTH // 2 + 30, HEIGHT // 2 + 70, 190, 70))

    def resume():
        try:
            if music_was_playing:
                pygame.mixer.music.unpause()
        except Exception:
            pass
        return "continue"

    def quit_game():
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        return "quit"

    while True:
        CLOCK.tick(FPS)

        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 155))
        SCREEN.blit(overlay, (0, 0))

        if not confirm:
            title = BIG.render("PAUSED", True, WHITE)
            SCREEN.blit(title, title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 150)))
            continue_btn.draw()
            quit_btn.draw()
        else:
            title = BIG.render("QUIT?", True, WHITE)
            SCREEN.blit(title, title.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 120)))
            yes_btn.draw()
            no_btn.draw()

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if confirm:
                        confirm = False
                    else:
                        return resume()

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not confirm:
                    if continue_btn.hit(event.pos):
                        return resume()
                    if quit_btn.hit(event.pos):
                        confirm = True
                else:
                    if yes_btn.hit(event.pos):
                        return quit_game()
                    if no_btn.hit(event.pos):
                        confirm = False

def game_loop(level_override=None):
    level = normalize_level(level_override) if level_override is not None else load_level()
    sx, sy = get_start(level)
    player = Player(sx, sy)
    cam = pygame.Vector2(0, 0)

    menu_btn = Button("MENU", (20, 20, 130, 50))
    edit_btn = Button("EDITOR", (170, 20, 160, 50))

    while True:
        CLOCK.tick(FPS)

        blocks = [rect_of(o) for o in level["objects"] if o["type"] == "block"]
        spikes = [rect_of(o) for o in level["objects"] if o["type"] == "spike"]
        finishes = [rect_of(o) for o in level["objects"] if o["type"] == "finish"]

        player.update(blocks)

        if player.rect.y > 4000 or any(player.rect.colliderect(s) for s in spikes):
            player = reset_player_to_start(level)

        if any(player.rect.colliderect(f) for f in finishes):
            player = reset_player_to_start(level)

        cam.x = player.rect.centerx - WIDTH // 2
        cam.y = player.rect.centery - HEIGHT // 2

        # В уровне фона-артефактов нет, только чистая сцена.
        draw_world(level, cam, editor=False, player=player)

        menu_btn.draw()
        edit_btn.draw()

        for event in pygame.event.get():
            player.handle_event(event)

            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    player = reset_player_to_start(level)
                elif event.key == pygame.K_ESCAPE:
                    result = game_pause_menu()
                    if result == "quit":
                        return

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if menu_btn.hit(event.pos):
                    return
                if edit_btn.hit(event.pos):
                    editor_loop()
                    level = load_level()
                    player = reset_player_to_start(level)

        pygame.display.flip()

def editor_loop():
    level = load_level()
    cam = pygame.Vector2(0, 0)

    selected_tool = "block"
    selected_index = None
    painting = False
    panning = False
    pan_start_mouse = pygame.Vector2(0, 0)
    pan_start_cam = pygame.Vector2(0, 0)
    last_painted = None

    buttons = [
        Button("BLOCK", (20, HEIGHT - PANEL_H + 30, 135, 60), "block"),
        Button("SPIKE", (170, HEIGHT - PANEL_H + 30, 135, 60), "spike"),
        Button("FINISH", (320, HEIGHT - PANEL_H + 30, 135, 60), "finish"),
        Button("START POS", (470, HEIGHT - PANEL_H + 30, 165, 60), "start"),
        Button("ERASE", (650, HEIGHT - PANEL_H + 30, 135, 60), "erase"),
        Button("SAVE", (WIDTH - 470, HEIGHT - PANEL_H + 30, 130, 60), "save"),
        Button("PLAY", (WIDTH - 320, HEIGHT - PANEL_H + 30, 130, 60), "play"),
        Button("MENU", (WIDTH - 170, HEIGHT - PANEL_H + 30, 130, 60), "menu"),
    ]

    while True:
        CLOCK.tick(FPS)
        draw_world(level, cam, editor=True, selected=selected_index)

        mx, my = pygame.mouse.get_pos()
        if my < HEIGHT - PANEL_H:
            gx, gy = cell_from_screen((mx, my), cam)
            preview = pygame.Rect(gx - cam.x, gy - cam.y, GRID, GRID)
            color = {"block": GRAY, "spike": PINK, "finish": GREEN, "start": YELLOW, "erase": RED}.get(selected_tool, WHITE)
            pygame.draw.rect(SCREEN, color, preview, 4)

        pygame.draw.rect(SCREEN, (12, 12, 15), (0, HEIGHT - PANEL_H, WIDTH, PANEL_H))
        pygame.draw.rect(SCREEN, RED, (0, HEIGHT - PANEL_H, WIDTH, 4))

        for b in buttons:
            b.draw(selected_tool == b.action)

        wx, wy = screen_to_world(mx, my, cam)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_level(level)
                pygame.quit()
                raise SystemExit

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked_button = False
                for b in buttons:
                    if b.hit(event.pos):
                        clicked_button = True
                        if b.action in ("block", "spike", "finish", "start", "erase"):
                            selected_tool = b.action
                        elif b.action == "save":
                            save_level(level)
                        elif b.action in ("play", "menu"):
                            save_level(level)
                            return
                        break

                if clicked_button or event.pos[1] >= HEIGHT - PANEL_H:
                    continue

                gx, gy = cell_from_screen(event.pos, cam)

                if selected_tool in DRAW_TOOLS:
                    painting = True
                    last_painted = None
                    place_cell(level, selected_tool, gx, gy)
                    selected_index = find_at(level, gx, gy)
                    last_painted = (gx, gy)
                else:
                    place_cell(level, selected_tool, gx, gy)
                    selected_index = find_at(level, gx, gy)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                panning = True
                pan_start_mouse = pygame.Vector2(event.pos)
                pan_start_cam = pygame.Vector2(cam)

            if event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    painting = False
                    last_painted = None
                if event.button == 3:
                    panning = False

            if event.type == pygame.MOUSEMOTION:
                if painting and event.pos[1] < HEIGHT - PANEL_H:
                    gx, gy = cell_from_screen(event.pos, cam)
                    if (gx, gy) != last_painted:
                        place_cell(level, selected_tool, gx, gy)
                        selected_index = find_at(level, gx, gy)
                        last_painted = (gx, gy)

                if panning:
                    mouse = pygame.Vector2(event.pos)
                    delta = mouse - pan_start_mouse
                    cam = pan_start_cam - delta

        pygame.display.flip()

if __name__ == "__main__":
    menu()
