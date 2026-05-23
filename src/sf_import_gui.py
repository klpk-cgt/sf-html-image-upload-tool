#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import mimetypes
import os
import re
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Callable, Iterable
from urllib.parse import quote, unquote, urlparse

import requests
from bs4 import BeautifulSoup, Comment

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except Exception:
    DND_FILES = None
    TkinterDnD = None
    DND_AVAILABLE = False


SF_UPLOAD_ENDPOINT = "https://serviceforce.lenovo.com.cn/api/wb/upload/file?token="
DEFAULT_IMAGE_STYLE = "max-width:100%;height:auto;display:block;margin:12px 0;"
ENCODINGS = ("auto", "utf-8", "gb18030", "gbk", "gb2312", "big5")
ENCODING_CANDIDATES = ("utf-8-sig", "utf-8", "gb18030", "gbk", "gb2312", "big5")
ALLOWED_TAGS = {
    "a", "b", "br", "em", "h1", "h2", "h3", "h4", "h5", "h6", "i", "img",
    "li", "ol", "p", "strong", "sub", "sup", "table", "tbody", "td", "tfoot",
    "th", "thead", "tr", "u", "ul",
}
TABLE_ATTRS = {"border", "cellpadding", "cellspacing", "colspan", "rowspan", "width"}
IMG_ATTRS = {"src", "alt", "width", "height", "style"}


class UploadError(RuntimeError):
    pass


@dataclass(frozen=True)
class DecodeResult:
    text: str
    encoding: str
    warning: str | None = None


class SfImportGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("SF HTML 图片上传转换工具")
        self.root.geometry("940x730")
        self.root.minsize(880, 660)
        self.html_files: list[Path] = []
        self.running = False
        self.token_var = tk.StringVar()
        self.image_dir_var = tk.StringVar()
        self.encoding_var = tk.StringVar(value="auto")
        self.clean_word_var = tk.BooleanVar(value=True)
        self.open_folder_var = tk.BooleanVar(value=True)
        self.show_token_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="可添加文件、选择HTML文件夹，或直接拖拽文件/文件夹到列表。")
        self._build_ui()
        self._enable_drag_drop()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)
        ttk.Label(outer, text="SF HTML 图片上传转换工具", font=("Microsoft YaHei UI", 16, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 10)
        )

        token_frame = ttk.LabelFrame(outer, text="1. 粘贴 SF 上传 token", padding=12)
        token_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        token_frame.columnconfigure(0, weight=1)
        self.token_entry = ttk.Entry(token_frame, textvariable=self.token_var, show="*")
        self.token_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Checkbutton(token_frame, text="显示", variable=self.show_token_var, command=self._toggle_token_visibility).grid(row=0, column=1)
        ttk.Label(token_frame, text="只填 token 即可；如果误粘完整 Request URL，程序也会自动兼容。", foreground="#555555").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        file_frame = ttk.LabelFrame(outer, text="2. 添加 HTML 文件", padding=12)
        file_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        file_frame.columnconfigure(0, weight=1)
        file_frame.rowconfigure(0, weight=1)
        list_wrap = ttk.Frame(file_frame)
        list_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)
        self.file_listbox = tk.Listbox(list_wrap, height=8, selectmode=tk.EXTENDED)
        self.file_listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL, command=self.file_listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.file_listbox.configure(yscrollcommand=scroll.set)
        ttk.Label(list_wrap, text="可拖拽 .htm/.html 文件，或拖拽文件夹自动识别里面的 HTML 文件。", foreground="#555555").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        buttons = ttk.Frame(file_frame)
        buttons.grid(row=0, column=1, sticky="ns")
        ttk.Button(buttons, text="添加HTML文件", command=self.add_files).pack(fill=tk.X, pady=(0, 8))
        ttk.Button(buttons, text="选择HTML文件夹", command=self.add_html_folder).pack(fill=tk.X, pady=(0, 8))
        ttk.Button(buttons, text="移除选中", command=self.remove_selected_files).pack(fill=tk.X, pady=(0, 8))
        ttk.Button(buttons, text="清空列表", command=self.clear_files).pack(fill=tk.X)

        option_frame = ttk.LabelFrame(outer, text="3. 图片目录与选项", padding=12)
        option_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        option_frame.columnconfigure(1, weight=1)
        ttk.Label(option_frame, text="图片文件夹").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(option_frame, textvariable=self.image_dir_var).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(option_frame, text="选择图片文件夹", command=self.choose_image_dir).grid(row=0, column=2)
        ttk.Label(option_frame, text="建议留空：程序会优先按每个 HTM 自动识别同名 .files 文件夹，找不到时才用这里选择的文件夹。", foreground="#555555").grid(
            row=1, column=1, columnspan=2, sticky="w", pady=(6, 8)
        )
        ttk.Label(option_frame, text="编码").grid(row=2, column=0, sticky="w", padx=(0, 8))
        ttk.Combobox(option_frame, textvariable=self.encoding_var, values=ENCODINGS, state="readonly", width=12).grid(row=2, column=1, sticky="w")
        ttk.Checkbutton(option_frame, text="清洗 Word HTML", variable=self.clean_word_var).grid(row=2, column=1, sticky="w", padx=(120, 0))
        ttk.Checkbutton(option_frame, text="完成后打开输出文件夹", variable=self.open_folder_var).grid(row=2, column=2)

        log_frame = ttk.LabelFrame(outer, text="运行日志", padding=12)
        log_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.configure(state=tk.DISABLED)

        bottom = ttk.Frame(outer)
        bottom.grid(row=5, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.dry_run_button = ttk.Button(bottom, text="预演检查（不上传）", command=lambda: self.start(True))
        self.dry_run_button.grid(row=0, column=1, padx=(0, 8))
        self.run_button = ttk.Button(bottom, text="开始正式转换", command=lambda: self.start(False))
        self.run_button.grid(row=0, column=2)
        ttk.Label(outer, textvariable=self.status_var, foreground="#333333").grid(row=6, column=0, sticky="w", pady=(8, 0))

    def _enable_drag_drop(self) -> None:
        if not DND_AVAILABLE:
            self.log("提示：当前环境未启用拖拽组件，仍可使用按钮添加文件或文件夹。")
            return
        for widget in (self.root, self.file_listbox, self.log_text):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.handle_drop)

    def handle_drop(self, event) -> None:
        added = self.add_paths(Path(item) for item in self.root.tk.splitlist(event.data))
        self.status_var.set(f"拖拽识别完成：新增 {added} 个 HTML 文件，当前共 {len(self.html_files)} 个。")

    def _toggle_token_visibility(self) -> None:
        self.token_entry.configure(show="" if self.show_token_var.get() else "*")

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(title="选择一个或多个 HTML 文件", filetypes=[("HTML 文件", "*.htm *.html"), ("所有文件", "*.*")])
        if paths:
            added = self.add_paths(Path(path) for path in paths)
            self.status_var.set(f"添加完成：新增 {added} 个 HTML 文件，当前共 {len(self.html_files)} 个。")

    def add_html_folder(self) -> None:
        path = filedialog.askdirectory(title="选择包含 HTML 文件的文件夹")
        if not path:
            return
        folder = Path(path)
        files = find_html_files_in_folder(folder)
        if not files:
            messagebox.showinfo("未找到 HTML", f"这个文件夹里没有找到 .htm/.html 文件：\n{folder}")
            return
        added = self.add_paths([folder])
        self.status_var.set(f"文件夹识别完成：找到 {len(files)} 个，新增 {added} 个，当前共 {len(self.html_files)} 个。")

    def add_paths(self, paths: Iterable[Path]) -> int:
        candidates: list[Path] = []
        for path in paths:
            if path.is_file() and path.suffix.lower() in {".htm", ".html"}:
                candidates.append(path)
            elif path.is_dir():
                candidates.extend(find_html_files_in_folder(path))
        existing = {str(path.resolve()).lower() for path in self.html_files}
        added = 0
        for path in sorted(candidates, key=lambda item: str(item).lower()):
            resolved = path.resolve()
            key = str(resolved).lower()
            if key in existing:
                continue
            self.html_files.append(resolved)
            existing.add(key)
            added += 1
        self.refresh_file_list()
        return added

    def remove_selected_files(self) -> None:
        selected = set(self.file_listbox.curselection())
        self.html_files = [path for index, path in enumerate(self.html_files) if index not in selected]
        self.refresh_file_list()

    def clear_files(self) -> None:
        self.html_files.clear()
        self.refresh_file_list()

    def refresh_file_list(self) -> None:
        self.file_listbox.delete(0, tk.END)
        for path in self.html_files:
            self.file_listbox.insert(tk.END, str(path))
        self.status_var.set(f"已选择 {len(self.html_files)} 个 HTML 文件。")

    def choose_image_dir(self) -> None:
        path = filedialog.askdirectory(title="选择图片文件夹")
        if path:
            self.image_dir_var.set(path)

    def start(self, dry_run: bool) -> None:
        if self.running:
            return
        if not self.html_files:
            messagebox.showwarning("缺少文件", "请先添加 HTML 文件，或选择一个包含 HTML 的文件夹。")
            return
        token_text = self.token_var.get().strip()
        if not dry_run and not token_text:
            messagebox.showwarning("缺少 token", "正式转换需要先粘贴 SF 上传 token。")
            return
        image_dir = Path(self.image_dir_var.get()).resolve() if self.image_dir_var.get().strip() else None
        if image_dir and not image_dir.exists():
            messagebox.showwarning("图片文件夹不存在", f"找不到图片文件夹：\n{image_dir}")
            return
        self.running = True
        self.set_buttons_state(tk.DISABLED)
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self.progress.configure(maximum=len(self.html_files), value=0)
        threading.Thread(target=self.run_batch, args=(list(self.html_files), token_text, image_dir, self.encoding_var.get(), self.clean_word_var.get(), dry_run), daemon=True).start()

    def run_batch(self, files: list[Path], token_text: str, image_dir: Path | None, encoding: str, clean_word: bool, dry_run: bool) -> None:
        upload_url = None if dry_run else build_upload_url(token_text)
        success_count = failed_count = 0
        output_dirs: set[Path] = set()
        self.log(f"模式：{'预演检查（不上传）' if dry_run else '正式转换'}")
        self.log(f"文件数量：{len(files)}")
        self.log(f"图片文件夹：{image_dir if image_dir else '自动识别'}\n")
        for position, html_path in enumerate(files, start=1):
            try:
                output_path, log_path = make_output_paths(html_path)
                self.log(f"({position}/{len(files)}) 开始处理：{html_path.name}")
                result = convert_one(html_path, image_dir, upload_url, output_path, log_path, encoding, clean_word, dry_run, self.log)
                if result["failed_count"]:
                    failed_count += 1
                    self.log(f"完成但有失败，详情见日志：{log_path}")
                else:
                    success_count += 1
                    self.log(f"完成：{output_path}")
                output_dirs.add(output_path.parent)
                self.log("")
            except Exception as exc:
                failed_count += 1
                self.log(f"处理失败：{html_path.name}\n原因：{exc}\n")
            finally:
                self.root.after(0, self.progress.configure, {"value": position})
        self.root.after(0, self.finish_batch, success_count, failed_count, sorted(output_dirs), dry_run)

    def finish_batch(self, success_count: int, failed_count: int, output_dirs: list[Path], dry_run: bool) -> None:
        self.running = False
        self.set_buttons_state(tk.NORMAL)
        self.status_var.set(f"完成：成功 {success_count} 个，失败/有失败项 {failed_count} 个。")
        if self.open_folder_var.get():
            for directory in output_dirs:
                try:
                    os.startfile(directory)
                except OSError:
                    self.log(f"无法自动打开文件夹：{directory}")
        messagebox.showinfo("预演完成" if dry_run else "转换完成", f"成功 {success_count} 个，失败/有失败项 {failed_count} 个。")

    def set_buttons_state(self, state: str) -> None:
        self.dry_run_button.configure(state=state)
        self.run_button.configure(state=state)

    def log(self, message: str) -> None:
        self.root.after(0, self._append_log, message)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)


def find_html_files_in_folder(folder: Path) -> list[Path]:
    try:
        return [
            path for path in folder.rglob("*")
            if path.is_file() and path.suffix.lower() in {".htm", ".html"} and "已转换" not in path.parts
        ]
    except OSError:
        return []


def make_output_paths(html_path: Path) -> tuple[Path, Path]:
    output_root = html_path.parent / "已转换"
    log_root = output_root / "转换日志"
    base = f"已转换_{html_path.stem}"
    index = 1
    while True:
        suffix = "" if index == 1 else f"_{index}"
        output_path = output_root / f"{base}{suffix}.txt"
        log_path = log_root / f"{base}{suffix}_日志.txt"
        if not output_path.exists() and not log_path.exists():
            return output_path, log_path
        index += 1


def build_upload_url(token_text: str) -> str:
    value = token_text.strip()
    if value.lower().startswith(("http://", "https://")):
        return value
    if "token=" in value:
        value = value.split("token=", 1)[1].split("&", 1)[0]
    return SF_UPLOAD_ENDPOINT + quote(value, safe="")


def convert_one(html_path: Path, image_dir: Path | None, upload_url: str | None, output_path: Path, log_path: Path, encoding: str, clean_word: bool, dry_run: bool, log: Callable[[str], None]) -> dict[str, int]:
    decoded = read_html(html_path, encoding)
    soup = BeautifulSoup(decoded.text, "html.parser")
    if clean_word:
        soup = clean_word_html(soup)
    resolved_image_dir = resolve_image_dir(None, html_path, soup) or image_dir
    result = process_images(soup, html_path, resolved_image_dir, upload_url, "file", DEFAULT_IMAGE_STYLE, dry_run, 60, log)
    write_text(output_path, render_output_html(soup, cleaned=clean_word))
    write_text(log_path, format_conversion_log(html_path, output_path, decoded.encoding, decoded.warning, resolved_image_dir, dry_run, result))
    log(f"HTML 编码：{decoded.encoding}")
    if decoded.warning:
        log(f"提示：{decoded.warning}")
    log(f"图片目录：{resolved_image_dir if resolved_image_dir else '未识别'}")
    log(f"图片标签：{result['total']}，已处理：{result['uploaded']}，跳过远程/data：{result['skipped']}，失败：{len(result['failed'])}")
    log(f"输出 TXT：{output_path}")
    log(f"转换日志：{log_path}")
    return {"total": int(result["total"]), "uploaded": int(result["uploaded"]), "failed_count": len(result["failed"])}


def read_html(path: Path, encoding: str) -> DecodeResult:
    raw = path.read_bytes()
    encoding = encoding.lower()
    if encoding != "auto":
        text = raw.decode(encoding, errors="replace")
        return DecodeResult(text=text, encoding=encoding, warning=encoding_warning(text))
    declared = detect_declared_encoding(raw)
    strict_results: list[tuple[int, str, str]] = []
    for candidate in unique_values([declared, *ENCODING_CANDIDATES]):
        try:
            text = raw.decode(candidate, errors="strict")
        except (LookupError, UnicodeDecodeError, TypeError):
            continue
        strict_results.append((decode_score(text), candidate, text))
    if strict_results:
        _, chosen_encoding, text = min(strict_results, key=lambda item: item[0])
        warning = encoding_warning(text)
        if declared and chosen_encoding != declared:
            warning = append_warning(warning, f"文件声明编码为 {declared}，实际使用 {chosen_encoding} 解码。")
        return DecodeResult(text=text, encoding=chosen_encoding, warning=warning)
    fallback = declared or "utf-8"
    text = raw.decode(fallback, errors="replace")
    return DecodeResult(text=text, encoding=fallback, warning=encoding_warning(text))


def detect_declared_encoding(raw: bytes) -> str | None:
    head = raw[:8192].decode("ascii", errors="ignore")
    for pattern in [r"<meta[^>]+charset=[\"']?\s*([a-zA-Z0-9_\-]+)", r"<meta[^>]+content=[\"'][^\"']*charset=\s*([a-zA-Z0-9_\-]+)"]:
        match = re.search(pattern, head, flags=re.IGNORECASE)
        if match:
            return {"gb2312": "gb18030", "gb-2312": "gb18030", "utf8": "utf-8"}.get(match.group(1).lower(), match.group(1).lower())
    return None


def decode_score(text: str) -> int:
    return sum(text.count(marker) * 20 for marker in ["\ufffd", "锟斤拷", "ï¿½", "Ã", "Â"]) + len(re.findall(r"[\u0080-\u009f]", text)) * 10


def encoding_warning(text: str) -> str | None:
    return "检测到疑似乱码字符；如果输出中文异常，请重试 gb18030 或 gbk。" if decode_score(text) > 0 else None


def append_warning(current: str | None, extra: str) -> str:
    return f"{current} {extra}" if current else extra


def unique_values(values: Iterable[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def clean_word_html(soup: BeautifulSoup) -> BeautifulSoup:
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    for tag_name in ("head", "style", "meta", "script", "link", "xml"):
        for tag in soup.find_all(tag_name):
            tag.decompose()
    if soup.body:
        soup = BeautifulSoup(soup.body.decode_contents(), "html.parser")
    for tag in list(soup.find_all(True)):
        name = tag.name.lower()
        if name not in ALLOWED_TAGS:
            tag.unwrap()
            continue
        allowed_attrs = IMG_ATTRS if name == "img" else ({"href", "title", "style"} if name == "a" else (TABLE_ATTRS | {"style"} if name in {"table", "td", "th"} else {"style"}))
        for attr in list(tag.attrs):
            if attr.lower() not in allowed_attrs:
                del tag.attrs[attr]
        if tag.has_attr("style"):
            style = clean_style(tag["style"])
            if style:
                tag["style"] = style
            else:
                del tag.attrs["style"]
        if name == "a" and not tag.get("href"):
            tag.unwrap()
    for tag in list(soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"])):
        if not tag.find("img") and not tag.find("br") and not tag.get_text().replace("\xa0", "").strip():
            tag.decompose()
    return soup


def clean_style(style: str) -> str:
    declarations: list[str] = []
    for raw in style.split(";"):
        if ":" not in raw:
            continue
        prop, value = raw.split(":", 1)
        prop = prop.strip().lower()
        value = value.strip()
        if prop.startswith("mso-") or prop.startswith("layout-grid") or prop in {"font-family", "page", "page-break-after", "page-break-before"} or "minorhansi" in value.lower():
            continue
        declarations.append(f"{prop}:{value}")
    return ";".join(declarations) + (";" if declarations else "")


def resolve_image_dir(value: str | None, html_path: Path, soup: BeautifulSoup) -> Path | None:
    html_dir = html_path.parent
    if value:
        path = Path(value)
        return path if path.is_absolute() else html_dir / path
    for candidate in [html_dir / f"{html_path.stem}.files", html_dir / f"{html_path.stem}_files", html_dir / "images", html_dir / "image", html_dir / "img"]:
        if candidate.is_dir():
            return candidate
    for img in soup.find_all("img"):
        src = img.get("src")
        if src and not is_remote_src(src) and not is_data_src(src):
            candidate = html_dir / Path(clean_local_src(src)).parent
            if candidate.is_dir():
                return candidate
    return None


def process_images(soup: BeautifulSoup, html_path: Path, image_dir: Path | None, upload_url: str | None, field_name: str, image_style: str, dry_run: bool, timeout: int, log_callback: Callable[[str], None] | None = None) -> dict[str, object]:
    mapping: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []
    uploaded = skipped = 0
    log = log_callback or print
    images = soup.find_all("img")
    for index, img in enumerate(images, start=1):
        old_src = img.get("src", "").strip()
        if image_style:
            img["style"] = image_style
        if not old_src:
            failed.append({"index": index, "old_src": old_src, "reason": "img 标签没有 src"})
            continue
        if is_remote_src(old_src) or is_data_src(old_src):
            skipped += 1
            mapping.append({"index": index, "old_src": old_src, "local_path": None, "new_url": old_src, "status": "skipped_remote"})
            continue
        local_path = find_local_image(old_src, html_path, image_dir)
        if not local_path:
            failed.append({"index": index, "old_src": old_src, "reason": "找不到本地图片"})
            continue
        try:
            new_url = f"DRY_RUN_URL/{local_path.name}" if dry_run else upload_image(upload_url, local_path, field_name, timeout)
            img["src"] = new_url
            uploaded += 1
            mapping.append({"index": index, "old_src": old_src, "local_path": str(local_path), "new_url": new_url, "status": "dry_run" if dry_run else "success"})
            log(f"[{index}] {'预演' if dry_run else '成功'}：{old_src} -> {new_url}")
        except UploadError as exc:
            failed.append({"index": index, "old_src": old_src, "local_path": str(local_path), "reason": str(exc)})
    return {"total": len(images), "uploaded": uploaded, "skipped": skipped, "mapping": mapping, "failed": failed}


def is_remote_src(src: str) -> bool:
    parsed = urlparse(src.strip())
    return parsed.scheme.lower() in {"http", "https"} or src.strip().startswith("//")


def is_data_src(src: str) -> bool:
    return src.strip().lower().startswith(("data:", "cid:"))


def clean_local_src(src: str) -> str:
    cleaned = html.unescape(src.strip())
    cleaned = unquote(cleaned).split("#", 1)[0].split("?", 1)[0]
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() == "file":
        path = unquote(parsed.path)
        if re.match(r"^/[a-zA-Z]:/", path):
            path = path[1:]
        return path.replace("/", "\\")
    return cleaned.replace("\\", "/")


def find_local_image(src: str, html_path: Path, image_dir: Path | None) -> Path | None:
    html_dir = html_path.parent
    clean_src = clean_local_src(src)
    src_path = Path(clean_src)
    basename = src_path.name
    candidates = [html_dir / clean_src, html_dir / f"{html_path.stem}.files" / basename, html_dir / f"{html_path.stem}_files" / basename, html_dir / "images" / basename, html_dir / basename]
    if src_path.is_absolute():
        candidates.insert(0, src_path)
    if image_dir:
        candidates.extend([image_dir / clean_src, image_dir / basename])
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    for root in [image_dir, html_dir]:
        if root and root.exists():
            for path in root.rglob("*"):
                if path.is_file() and path.name.lower() == basename.lower():
                    return path.resolve()
    return None


def upload_image(upload_url: str | None, image_path: Path, field_name: str, timeout: int) -> str:
    if not upload_url:
        raise UploadError("缺少上传 token")
    mime_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
    with image_path.open("rb") as file_obj:
        response = requests.post(upload_url, files={field_name: (image_path.name, file_obj, mime_type)}, timeout=timeout)
    if response.status_code in {401, 403}:
        raise UploadError("上传失败，可能是 token 过期。请重新登录 SF 后复制新 token。")
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    url = data.get("url") if isinstance(data, dict) else None
    if not url:
        raise UploadError("上传成功但未在响应中找到 data.url，请检查接口返回结构。")
    return str(url).replace("\\/", "/")


def render_output_html(soup: BeautifulSoup, cleaned: bool) -> str:
    return (soup.decode(formatter="html") if cleaned else str(soup)).strip() + "\n"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def format_conversion_log(html_path: Path, output_path: Path, decoded_encoding: str, encoding_warning: str | None, image_dir: Path | None, dry_run: bool, result: dict[str, object]) -> str:
    lines = [
        "SF HTML 图片转换日志", "=" * 28,
        f"模式：{'预演检查（不上传）' if dry_run else '正式转换'}",
        f"输入 HTML：{html_path}", f"输出 TXT：{output_path}", f"HTML 编码：{decoded_encoding}",
        f"图片目录：{image_dir if image_dir else '未识别'}", f"图片标签：{result['total']}",
        f"已处理本地图片：{result['uploaded']}", f"跳过远程/data 图片：{result['skipped']}", f"失败：{len(result['failed'])}",
    ]
    if encoding_warning:
        lines.append(f"编码提示：{encoding_warning}")
    lines.extend(["", "图片处理明细", "-" * 28])
    for item in result["mapping"]:
        lines.extend([f"[{item.get('index')}] {item.get('status')}", f"原地址：{item.get('old_src')}", f"本地文件：{item.get('local_path') or ''}", f"新地址：{item.get('new_url')}", ""])
    if not result["mapping"]:
        lines.append("无成功或跳过记录。")
    lines.extend(["", "失败明细", "-" * 28])
    for item in result["failed"]:
        lines.extend([f"[{item.get('index')}] {item.get('reason')}", f"原地址：{item.get('old_src')}", f"本地文件：{item.get('local_path', '')}", ""])
    if not result["failed"]:
        lines.append("无失败项。")
    return "\n".join(lines).rstrip() + "\n"


def create_root() -> tk.Tk:
    return TkinterDnD.Tk() if DND_AVAILABLE and TkinterDnD is not None else tk.Tk()


def main() -> None:
    root = create_root()
    icon_path = Path(sys.executable).with_name("sf_html_tool.ico") if getattr(sys, "frozen", False) else Path(__file__).with_name("sf_html_tool.ico")
    if icon_path.exists():
        try:
            root.iconbitmap(str(icon_path))
        except tk.TclError:
            pass
    SfImportGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
