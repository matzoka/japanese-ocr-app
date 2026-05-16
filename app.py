# ============================================================
#  日本語OCRアプリ
#  エンジン: RapidOCR / Mistral OCR / PaddleOCR-VL
#  対応: 日本語 / 英語 / 数字 混在PDF
# ============================================================

import base64
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import concurrent.futures
import sys
import threading
import traceback

from japanize import japanize

PADDLE_VL_RENDER_DPI = 150
PADDLE_VL_MAX_IMAGE_SIDE = 1600
PADDLE_VL_MAX_PIXELS = 1600 * 1600


class OCRApp:
    ENGINE_RAPID = "RapidOCR（ローカル・無料）"
    ENGINE_MISTRAL = "Mistral OCR（API・高精度）"
    ENGINE_PADDLE_VL = "PaddleOCR-VL（無料・高精度）"

    COLOR_BG         = "#1e2a38"
    COLOR_ACCENT     = "#2ecc71"
    COLOR_BTN_BLUE   = "#2980b9"
    COLOR_BTN_PURPLE = "#8e44ad"
    COLOR_BTN_GRAY   = "#636e72"
    COLOR_BTN_RED    = "#e74c3c"
    COLOR_TEXT       = "#ecf0f1"
    COLOR_PANEL      = "#2c3e50"
    FONT_JA          = "Yu Gothic UI"

    TEXT_LAYER_MIN_LENGTH = 40
    TEXT_LAYER_MIN_PAGE_CHARS = 60

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Japanese OCR App  -  Multi Engine OCR")
        self.root.geometry("860x710")
        self.root.minsize(700, 550)
        self.root.configure(bg=self.COLOR_BG)

        self.ocr_result = ""
        self._rapid_engine = None
        self._paddle_vl_pipeline = None
        self._api_style = None
        self._cancel_flag = False
        self._elapsed_status_active = False
        self._elapsed_started_at = None
        self._elapsed_phase = ""
        self._elapsed_done_pages = 0
        self._build_ui()

    # ── UI ───────────────────────────────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self.root, bg=self.COLOR_PANEL, pady=12)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="日本語 OCR アプリ",
                 font=(self.FONT_JA, 17, "bold"),
                 fg=self.COLOR_ACCENT, bg=self.COLOR_PANEL).pack()
        tk.Label(hdr, text="日本語・英語・数字の混在 PDF に対応  |  RapidOCR / Mistral OCR / PaddleOCR-VL",
                 font=(self.FONT_JA, 9),
                 fg="#95a5a6", bg=self.COLOR_PANEL).pack()

        self._build_row("PDF ファイル", "file")
        self._build_row("テキスト保存先フォルダ", "output")
        self._build_engine_row()
        self._build_api_key_row()

        btn_row = tk.Frame(self.root, bg=self.COLOR_BG, pady=8)
        btn_row.pack()
        self.ocr_btn = self._btn(btn_row, "OCR 開始",
                                  self.COLOR_ACCENT, self.start_ocr, bold=True)
        self.ocr_btn.pack(side=tk.LEFT, padx=6)

        self.cancel_btn = self._btn(btn_row, "キャンセル",
                                     self.COLOR_BTN_RED, self._cancel_ocr)
        self.cancel_btn.config(state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=6)

        self.save_btn = self._btn(btn_row, "テキスト保存",
                                   self.COLOR_BTN_PURPLE, self.save_result)
        self.save_btn.config(state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT, padx=6)

        self._btn(btn_row, "クリア",
                   self.COLOR_BTN_GRAY, self.clear_all).pack(side=tk.LEFT, padx=6)

        sf = tk.Frame(self.root, bg=self.COLOR_BG)
        sf.pack(fill=tk.X, padx=16, pady=(0, 4))
        self.status_var = tk.StringVar(value="ファイルを選択して OCR 開始を押してください")
        tk.Label(sf, textvariable=self.status_var,
                 font=(self.FONT_JA, 9), fg="#b2bec3", bg=self.COLOR_BG,
                 anchor=tk.W).pack(fill=tk.X)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("green.Horizontal.TProgressbar",
                        troughcolor=self.COLOR_PANEL,
                        background=self.COLOR_ACCENT)
        self.progress = ttk.Progressbar(sf,
                                         style="green.Horizontal.TProgressbar",
                                         mode="indeterminate")
        self.progress.pack(fill=tk.X, pady=(2, 0))

        rf = tk.LabelFrame(self.root, text="  OCR 結果  ",
                            font=(self.FONT_JA, 10, "bold"),
                            fg=self.COLOR_TEXT, bg=self.COLOR_BG,
                            labelanchor="nw", padx=8, pady=8,
                            relief=tk.FLAT, bd=1)
        rf.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 14))

        self.result_text = scrolledtext.ScrolledText(
            rf, font=(self.FONT_JA, 11), wrap=tk.WORD,
            bg="#1a252f", fg=self.COLOR_TEXT,
            insertbackground=self.COLOR_TEXT,
            selectbackground=self.COLOR_BTN_BLUE,
            relief=tk.FLAT, state=tk.DISABLED)
        self.result_text.pack(fill=tk.BOTH, expand=True)

    def _build_row(self, label, key):
        f = tk.Frame(self.root, bg=self.COLOR_BG)
        f.pack(fill=tk.X, padx=16, pady=(10, 0))
        tk.Label(f, text=label,
                 font=(self.FONT_JA, 9, "bold"),
                 fg="#95a5a6", bg=self.COLOR_BG, width=18,
                 anchor=tk.W).pack(side=tk.LEFT)
        var = tk.StringVar()
        setattr(self, f"{key}_var", var)
        tk.Entry(f, textvariable=var,
                 font=(self.FONT_JA, 10),
                 bg=self.COLOR_PANEL, fg=self.COLOR_TEXT,
                 insertbackground=self.COLOR_TEXT,
                 relief=tk.FLAT, bd=4).pack(side=tk.LEFT, fill=tk.X, expand=True)
        cmd = self.browse_file if key == "file" else self.browse_output
        self._btn(f, "参照...", self.COLOR_BTN_BLUE, cmd,
                   pady=4).pack(side=tk.RIGHT, padx=(6, 0))

    def _build_engine_row(self):
        f = tk.Frame(self.root, bg=self.COLOR_BG)
        f.pack(fill=tk.X, padx=16, pady=(10, 0))
        tk.Label(f, text="OCR エンジン",
                 font=(self.FONT_JA, 9, "bold"),
                 fg="#95a5a6", bg=self.COLOR_BG, width=18,
                 anchor=tk.W).pack(side=tk.LEFT)

        self.engine_var = tk.StringVar(value=self.ENGINE_RAPID)
        self.engine_combo = ttk.Combobox(
            f,
            textvariable=self.engine_var,
            values=(self.ENGINE_RAPID, self.ENGINE_MISTRAL, self.ENGINE_PADDLE_VL),
            state="readonly",
            font=(self.FONT_JA, 10),
        )
        self.engine_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _build_api_key_row(self):
        f = tk.Frame(self.root, bg=self.COLOR_BG)
        f.pack(fill=tk.X, padx=16, pady=(10, 0))
        tk.Label(f, text="Mistral API キー",
                 font=(self.FONT_JA, 9, "bold"),
                 fg="#95a5a6", bg=self.COLOR_BG, width=18,
                 anchor=tk.W).pack(side=tk.LEFT)
        self.api_key_var = tk.StringVar(
            value=os.environ.get("MISTRAL_API_KEY", ""))
        self._api_key_entry = tk.Entry(
            f, textvariable=self.api_key_var,
            font=(self.FONT_JA, 10), show="*",
            bg=self.COLOR_PANEL, fg=self.COLOR_TEXT,
            insertbackground=self.COLOR_TEXT,
            relief=tk.FLAT, bd=4)
        self._api_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._show_key = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="表示", variable=self._show_key,
                       command=self._toggle_api_key_visibility,
                       font=(self.FONT_JA, 9),
                       fg="#95a5a6", bg=self.COLOR_BG,
                       selectcolor=self.COLOR_PANEL,
                       activebackground=self.COLOR_BG,
                       activeforeground="#95a5a6").pack(side=tk.RIGHT, padx=(6, 0))

    def _toggle_api_key_visibility(self):
        self._api_key_entry.config(
            show="" if self._show_key.get() else "*")

    def _btn(self, parent, text, color, cmd, bold=False, pady=8):
        fg = "#1e2a38" if color == self.COLOR_ACCENT else "white"
        return tk.Button(parent, text=text, command=cmd,
                         font=(self.FONT_JA, 11, "bold" if bold else "normal"),
                         bg=color, fg=fg, activebackground=color,
                         relief=tk.FLAT, padx=14, pady=pady, cursor="hand2")

    # ── ダイアログ ───────────────────────────────────────────
    def browse_file(self):
        path = filedialog.askopenfilename(
            title="PDF ファイルを選択",
            filetypes=[("PDF ファイル", "*.pdf"), ("すべてのファイル", "*.*")])
        if path:
            self.file_var.set(path)
            if not self.output_var.get():
                self.output_var.set(os.path.dirname(path))

    def browse_output(self):
        path = filedialog.askdirectory(title="保存先フォルダを選択")
        if path:
            self.output_var.set(path)

    # ── OCR ──────────────────────────────────────────────────
    def start_ocr(self):
        pdf_path = self.file_var.get().strip()
        if not pdf_path or not os.path.isfile(pdf_path):
            messagebox.showerror("Error", "有効な PDF ファイルを選択してください。")
            return
        engine_name = self.engine_var.get()
        if engine_name == self.ENGINE_MISTRAL:
            api_key = (self.api_key_var.get().strip()
                       or os.environ.get("MISTRAL_API_KEY", "").strip())
            if not api_key:
                messagebox.showerror(
                    "Error",
                    "Mistral OCR を使うには API キーが必要です。\n"
                    "API キー欄に入力するか、環境変数 MISTRAL_API_KEY を設定してください。")
                return
        if engine_name == self.ENGINE_PADDLE_VL:
            messagebox.showwarning(
                "PaddleOCR-VL",
                "この環境ではCPU実行です。時間がかかります。"
            )
        self._cancel_flag = False
        self.ocr_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.save_btn.config(state=tk.DISABLED)
        self.engine_combo.config(state=tk.DISABLED)
        self._clear_result()
        self.progress.start(10)
        threading.Thread(target=self._run_ocr,
                         args=(pdf_path, engine_name), daemon=True).start()

    def _cancel_ocr(self):
        self._cancel_flag = True
        self.cancel_btn.config(state=tk.DISABLED)
        self._status("キャンセル中...")

    def _init_rapid_engine(self):
        try:
            from rapidocr import LangRec, OCRVersion, RapidOCR
            try:
                engine = RapidOCR(params={
                    "Rec.lang_type": LangRec.JAPAN,
                    "Rec.ocr_version": OCRVersion.PPOCRV4,
                })
            except Exception as exc:
                raise RuntimeError(
                    "RapidOCR の日本語モデル初期化に失敗しました。"
                    " rapidocr パッケージを更新して setup.bat を再実行してください。"
                ) from exc
            return engine, "new"
        except ImportError:
            pass

        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR(), "legacy"

    def _extract_texts(self, result, api_style):
        if api_style == "new" and hasattr(result, "txts"):
            txts = result.txts
            return list(txts) if txts else []

        if isinstance(result, tuple):
            data = result[0]
        else:
            data = result

        if not data:
            return []

        texts = []
        for item in data:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                texts.append(item[1])
        return texts

    def _run_ocr(self, pdf_path, engine_name):
        if engine_name == self.ENGINE_MISTRAL:
            self._run_mistral_ocr(pdf_path)
        elif engine_name == self.ENGINE_PADDLE_VL:
            self._run_paddle_vl_ocr(pdf_path)
        else:
            self._run_rapid_ocr(pdf_path)

    def _run_rapid_ocr(self, pdf_path):
        try:
            self._start_elapsed_status("PDF 読み込み中")
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(pdf_path)
            total = len(pdf)
            self._stop_elapsed_status()

            try:
                text_layer = self._extract_pdf_text_layer(pdf, total)
                if text_layer.strip():
                    self.ocr_result = text_layer
                    self._show_result(self.ocr_result)
                    self._status(
                        f"完了！ PDF内のテキスト層から {total} ページを抽出しました。"
                    )
                    return

                if self._rapid_engine is None:
                    self._start_elapsed_status("RapidOCR 初期化中")
                    self._rapid_engine, self._api_style = self._init_rapid_engine()
                    self._stop_elapsed_status()

                import numpy as np
                lines = []

                self._start_elapsed_status(f"OCR 処理中 {total}ページ")
                for i in range(total):
                    if self._cancel_flag:
                        lines.append("\n（ユーザーによりキャンセルされました）")
                        break

                    self._set_elapsed_phase(
                        f"OCR 処理中 {i + 1}/{total}", done_pages=i)

                    bitmap = pil_img = img_array = None
                    try:
                        page = pdf[i]
                        bitmap = page.render(scale=300 / 72)
                        pil_img = bitmap.to_pil().convert("RGB")
                        img_array = np.array(pil_img)

                        result = self._rapid_engine(img_array)
                        texts = self._extract_texts(result, self._api_style)

                        self._add_page_separator(lines, i + 1, total)

                        if texts:
                            for t in texts:
                                if t and t.strip():
                                    lines.append(japanize(t))
                        else:
                            lines.append(
                                "（このページからテキストを検出できませんでした）")
                        lines.append("")
                    except Exception as page_err:
                        self._add_page_separator(lines, i + 1, total)
                        lines.append(
                            f"（ページ {i + 1} でエラー: {page_err}）")
                        lines.append("")
                    finally:
                        if bitmap is not None:
                            del bitmap, pil_img, img_array

                    self._set_elapsed_phase(
                        f"OCR 処理中 {i + 1}/{total}", done_pages=i + 1)

                self._stop_elapsed_status()
            finally:
                pdf.close()

            self.ocr_result = "\n".join(lines)
            self._show_result(self.ocr_result)
            if not self._cancel_flag:
                self._status(f"完了！ {total} ページを処理しました。")

        except ImportError as exc:
            self._stop_elapsed_status()
            self._show_error(
                f"必要なモジュールが見つかりません:\n{exc}\n\n"
                "setup.bat を実行してインストールしてください。")
            self._status("エラー: モジュールが不足しています")
        except Exception:
            self._stop_elapsed_status()
            err = traceback.format_exc()
            self._show_error(f"OCR 処理中にエラーが発生しました:\n\n{err}")
            self._status("エラーが発生しました")
        finally:
            self.root.after(0, self._ocr_done)

    def _extract_pdf_text_layer(self, pdf, total):
        lines = []
        has_substantial = False

        self._start_elapsed_status(f"テキスト層確認中 {total}ページ")
        for i in range(total):
            if self._cancel_flag:
                break
            self._set_elapsed_phase(
                f"テキスト層確認中 {i + 1}/{total}", done_pages=i)

            try:
                page = pdf[i]
                text_page = page.get_textpage()
                text = text_page.get_text_range()
            except Exception:
                text = ""

            text = self._clean_pdf_text_layer(text)
            if len(text) >= self.TEXT_LAYER_MIN_PAGE_CHARS:
                has_substantial = True
            if not text:
                self._set_elapsed_phase(
                    f"テキスト層確認中 {i + 1}/{total}", done_pages=i + 1)
                continue

            self._add_page_separator(lines, i + 1, total)
            lines.append(japanize(text))
            lines.append("")

            self._set_elapsed_phase(
                f"テキスト層確認中 {i + 1}/{total}", done_pages=i + 1)

        self._stop_elapsed_status()

        result = "\n".join(lines).strip()
        if has_substantial or len(result) >= self.TEXT_LAYER_MIN_LENGTH:
            return result
        return ""

    def _clean_pdf_text_layer(self, text):
        return (
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\ufffe", "-")
            .replace("\u00ad", "")
            .strip()
        )

    def _init_paddle_vl_pipeline(self):
        try:
            import paddle
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR-VL の推論エンジン paddlepaddle が未インストールです。\n\n"
                "setup_paddle_vl.bat を実行してから、アプリを再起動してください。\n"
                "Windows ネイティブ環境で動かない場合は、PaddleOCR-VL の公式推奨どおり "
                "WSL / Docker / GPU 環境での実行を検討してください。"
            ) from exc

        try:
            paddle.utils.run_check()
        except Exception as exc:
            raise RuntimeError(
                "paddlepaddle は見つかりましたが、現在の環境では正常に動作確認できませんでした。\n\n"
                "PaddleOCR-VL は環境依存が強いため、Windows ネイティブ環境では "
                "WSL / Docker / GPU 環境が必要になる場合があります。"
            ) from exc

        try:
            from paddleocr import PaddleOCRVL
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR-VL を使うには追加セットアップが必要です。\n\n"
                "setup_paddle_vl.bat を実行して、paddlepaddle と "
                "paddleocr[doc-parser] をインストールしてください。"
            ) from exc

        kwargs = {
            "pipeline_version": "v1.5",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_chart_recognition": False,
            "use_seal_recognition": False,
        }
        engine = os.environ.get("PADDLEOCR_VL_ENGINE", "").strip()
        device = os.environ.get("PADDLEOCR_VL_DEVICE", "").strip()
        if engine:
            kwargs["engine"] = engine
        if device:
            kwargs["device"] = device

        return PaddleOCRVL(**kwargs)

    def _run_paddle_vl_ocr(self, pdf_path):
        try:
            if self._paddle_vl_pipeline is None:
                self._start_elapsed_status("PaddleOCR-VL 初期化中")
                self._paddle_vl_pipeline = self._init_paddle_vl_pipeline()
                self._stop_elapsed_status()

            self._start_elapsed_status("PaddleOCR-VL 推論中")
            with tempfile.TemporaryDirectory(prefix="paddleocr_vl_") as output_dir:
                page_images = self._render_pdf_for_paddle_vl(
                    pdf_path, Path(output_dir))
                total = len(page_images)

                if total == 0:
                    self.ocr_result = "（PDF から画像を生成できませんでした）"
                    self._show_result(self.ocr_result)
                    self._status("エラー: PDF ページ画像の生成に失敗しました")
                    return

                for page_no, page_image in enumerate(page_images, start=1):
                    if self._cancel_flag:
                        self.ocr_result = "\n".join(
                            self._read_markdown_parts(Path(output_dir)))
                        if not self.ocr_result.strip():
                            self.ocr_result = "（ユーザーによりキャンセルされました）"
                        self._show_result(self.ocr_result)
                        self._status("キャンセルされました")
                        return

                    self._set_elapsed_phase(
                        f"PaddleOCR-VL 推論中 {page_no}/{total}",
                        done_pages=page_no - 1,
                    )
                    try:
                        print(f"[PaddleOCR-VL] ページ {page_no}/{total} 推論開始...",
                              flush=True)
                        executor = concurrent.futures.ThreadPoolExecutor(
                            max_workers=1)
                        try:
                            future = executor.submit(
                                self._paddle_vl_pipeline.predict,
                                input=str(page_image),
                                use_doc_orientation_classify=False,
                                use_doc_unwarping=False,
                                use_chart_recognition=False,
                                use_seal_recognition=False,
                                max_pixels=PADDLE_VL_MAX_PIXELS,
                                max_new_tokens=1024,
                            )
                            output = future.result(timeout=600)
                        finally:
                            executor.shutdown(wait=False)
                        print(f"[PaddleOCR-VL] ページ {page_no}/{total} 推論完了",
                              flush=True)
                        for res in output:
                            res.save_to_markdown(save_path=output_dir)
                        print(f"[PaddleOCR-VL] ページ {page_no}/{total} Markdown保存完了",
                              flush=True)
                    except concurrent.futures.TimeoutError:
                        page_image.unlink(missing_ok=True)
                        raise RuntimeError(
                            f"PaddleOCR-VL の推論がタイムアウトしました（{page_no}ページ目）。\n"
                            "CPU 環境では正しく動作しない可能性があります。\n"
                            "RapidOCR エンジンをお試しください。"
                        )
                    except Exception as page_err:
                        page_image.unlink(missing_ok=True)
                        raise RuntimeError(
                            f"PaddleOCR-VL 推論中にエラー（{page_no}ページ目）: {page_err}"
                        )

                    self._set_elapsed_phase(
                        f"PaddleOCR-VL 推論中 {page_no}/{total}",
                        done_pages=page_no,
                    )

                markdown = self._read_markdown_output(Path(output_dir))

            self.ocr_result = (
                japanize(markdown.strip())
                if markdown.strip()
                else "（PaddleOCR-VL からテキストを取得できませんでした）"
            )
            self._show_result(self.ocr_result)
            self._status("完了！ PaddleOCR-VL で処理しました。")

        except RuntimeError as exc:
            self._show_error(f"PaddleOCR-VL 処理中にエラーが発生しました:\n\n{exc}")
            self._status("エラーが発生しました")
        except Exception:
            err = traceback.format_exc()
            self._show_error(f"PaddleOCR-VL 処理中にエラーが発生しました:\n\n{err}")
            self._status("エラーが発生しました")
        finally:
            self._stop_elapsed_status()
            self.root.after(0, self._ocr_done)

    def _run_mistral_ocr(self, pdf_path):
        try:
            api_key = (self.api_key_var.get().strip()
                       or os.environ.get("MISTRAL_API_KEY", "").strip())
            if not api_key:
                raise RuntimeError(
                    "Mistral OCR を使うには API キーが必要です。\n"
                    "API キー欄に入力するか、環境変数 MISTRAL_API_KEY を設定してください。"
                )

            self._start_elapsed_status("Mistral OCR 初期化中")
            try:
                from mistralai.client import Mistral
            except ImportError:
                from mistralai import Mistral

            client = Mistral(api_key=api_key)

            self._set_elapsed_phase("PDF を base64 に変換中")
            with open(pdf_path, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode("ascii")

            self._set_elapsed_phase("Mistral API 処理中")
            ocr_response = client.ocr.process(
                model="mistral-ocr-latest",
                document={
                    "type": "document_url",
                    "document_url": f"data:application/pdf;base64,{base64_pdf}",
                },
                include_image_base64=False,
            )

            pages = getattr(ocr_response, "pages", None) or []
            lines = []
            total = len(pages)
            for idx, page in enumerate(pages):
                if self._cancel_flag:
                    lines.append("\n（ユーザーによりキャンセルされました）")
                    break

                self._set_elapsed_phase(
                    f"結果を整形中 {idx + 1}/{total}", done_pages=idx)

                try:
                    markdown = getattr(page, "markdown", None)
                    if markdown is None and isinstance(page, dict):
                        markdown = page.get("markdown")
                    markdown = markdown or ""

                    page_index = getattr(page, "index", idx)
                    if isinstance(page, dict):
                        page_index = page.get("index", idx)

                    self._add_page_separator(
                        lines, int(page_index) + 1, total)

                    content = japanize(markdown.strip()) if markdown.strip() else ""
                    lines.append(
                        content or "（このページからテキストを検出できませんでした）")
                    lines.append("")
                except Exception as page_err:
                    self._add_page_separator(
                        lines, idx + 1, total)
                    lines.append(
                        f"（ページ {idx + 1} でエラー: {page_err}）")
                    lines.append("")

                self._set_elapsed_phase(
                    f"結果を整形中 {idx + 1}/{total}", done_pages=idx + 1)

            if not lines:
                lines.append("（Mistral OCR からテキストを取得できませんでした）")

            self.ocr_result = "\n".join(lines)
            self._show_result(self.ocr_result)
            if not self._cancel_flag:
                self._status(f"完了！ Mistral OCR で {total} ページを処理しました。")

        except ImportError as exc:
            self._show_error(
                f"Mistral OCR 用のモジュールが見つかりません:\n{exc}\n\n"
                "setup.bat を実行して mistralai をインストールしてください。")
            self._status("エラー: mistralai モジュールが不足しています")
        except Exception:
            err = traceback.format_exc()
            self._show_error(f"Mistral OCR 処理中にエラーが発生しました:\n\n{err}")
            self._status("エラーが発生しました")
        finally:
            self._stop_elapsed_status()
            self.root.after(0, self._ocr_done)

    # ── ヘルパー ─────────────────────────────────────────────
    def _add_page_separator(self, lines, page_num, total):
        if total > 1:
            lines.append(f"\n{'─' * 40}")
            lines.append(f"  ページ {page_num} / {total}")
            lines.append(f"{'─' * 40}\n")

    def _read_markdown_parts(self, output_dir: Path):
        md_files = sorted(output_dir.rglob("*.md"))
        parts = []
        for idx, md_file in enumerate(md_files):
            text = md_file.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                continue
            parts.append(text)
        return parts

    def _read_markdown_output(self, output_dir: Path) -> str:
        md_files = sorted(output_dir.rglob("*.md"))
        parts = []
        for idx, md_file in enumerate(md_files):
            text = md_file.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                continue
            self._add_page_separator(parts, idx + 1, len(md_files))
            parts.append(text)
            parts.append("")
        return "\n".join(parts)

    def _render_pdf_for_paddle_vl(self, pdf_path, output_dir: Path):
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(pdf_path)
        image_paths = []
        total = len(pdf)
        try:
            for i in range(total):
                if self._cancel_flag:
                    break
                self._set_elapsed_phase(
                    f"PaddleOCR-VL 前処理中 {i + 1}/{total}", done_pages=i)
                page = pdf[i]
                bitmap = page.render(scale=PADDLE_VL_RENDER_DPI / 72)
                pil_img = bitmap.to_pil().convert("RGB")
                pil_img.thumbnail(
                    (PADDLE_VL_MAX_IMAGE_SIDE, PADDLE_VL_MAX_IMAGE_SIDE)
                )
                image_path = output_dir / f"paddle_vl_page_{i + 1:04d}.png"
                pil_img.save(image_path)
                image_paths.append(image_path)
                del bitmap, pil_img
        finally:
            pdf.close()
        return image_paths

    def _start_elapsed_status(self, phase):
        self._elapsed_status_active = True
        self._elapsed_started_at = time.monotonic()
        self._elapsed_phase = phase
        self._elapsed_done_pages = 0
        self.root.after(0, self._tick_elapsed_status)

    def _set_elapsed_phase(self, phase, done_pages=None):
        self._elapsed_phase = phase
        if done_pages is not None:
            self._elapsed_done_pages = done_pages

    def _stop_elapsed_status(self):
        self._elapsed_status_active = False

    def _tick_elapsed_status(self):
        if not self._elapsed_status_active or self._elapsed_started_at is None:
            return

        elapsed = int(time.monotonic() - self._elapsed_started_at)
        minutes, seconds = divmod(elapsed, 60)
        page_msg = ""
        if self._elapsed_done_pages:
            page_msg = f" / 完了ページ: {self._elapsed_done_pages}"
        self.status_var.set(
            f"{self._elapsed_phase}... 経過 {minutes:02d}:{seconds:02d}{page_msg}"
        )
        self.root.after(1000, self._tick_elapsed_status)

    def _ocr_done(self):
        self.progress.stop()
        self.ocr_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.engine_combo.config(state="readonly")
        if self.ocr_result.strip():
            self.save_btn.config(state=tk.NORMAL)

    # ── 保存 ─────────────────────────────────────────────────
    def save_result(self):
        if not self.ocr_result:
            return
        out_dir = self.output_var.get().strip() or os.path.expanduser("~")
        base = os.path.splitext(os.path.basename(self.file_var.get()))[0]
        save_path = filedialog.asksaveasfilename(
            initialdir=out_dir,
            initialfile=f"{base}_ocr.txt",
            title="テキストを保存",
            defaultextension=".txt",
            filetypes=[("テキストファイル", "*.txt"), ("すべてのファイル", "*.*")])
        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(self.ocr_result)
            messagebox.showinfo("保存完了", f"保存しました:\n{save_path}")

    # ── クリア ───────────────────────────────────────────────
    def clear_all(self):
        self._cancel_flag = True
        self.file_var.set("")
        self.output_var.set("")
        self._clear_result()
        self.ocr_result = ""
        self.save_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.DISABLED)
        self.status_var.set("ファイルを選択して OCR 開始を押してください")

    # ── ユーティリティ ───────────────────────────────────────
    def _status(self, msg):
        self.root.after(0, lambda: self.status_var.set(msg))

    def _clear_result(self):
        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete(1.0, tk.END)
        self.result_text.config(state=tk.DISABLED)

    def _show_result(self, text):
        def _u():
            self.result_text.config(state=tk.NORMAL)
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, text)
            self.result_text.config(state=tk.DISABLED)
        self.root.after(0, _u)

    def _show_error(self, msg):
        self.root.after(0, lambda: messagebox.showerror("Error", msg))


# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = OCRApp(root)
    root.mainloop()
