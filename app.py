# ============================================================
#  日本語OCRアプリ
#  エンジン: RapidOCR / Mistral OCR / Surya OCR
#  対応: 日本語 / 英語 / 数字 混在PDF
# ============================================================

import base64
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import traceback

from japanize import japanize


class OCRApp:
    ENGINE_RAPID = "RapidOCR（ローカル・無料）"
    ENGINE_MISTRAL = "Mistral OCR（API・高精度）"
    ENGINE_SURYA = "Surya OCR（無料・高品質）"

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
        self._surya_engine = None
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
        tk.Label(hdr, text="日本語・英語・数字の混在 PDF に対応  |  RapidOCR / Mistral OCR / Surya OCR",
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
            values=(self.ENGINE_RAPID, self.ENGINE_MISTRAL, self.ENGINE_SURYA),
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
        elif engine_name == self.ENGINE_SURYA:
            self._run_surya_ocr(pdf_path)
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

    def _init_surya_engine(self):
        try:
            from surya.detection import DetectionPredictor
            from surya.foundation import FoundationPredictor
            from surya.recognition import RecognitionPredictor
            from surya.layout import LayoutPredictor
            from surya.table_rec import TableRecPredictor
            from surya.common.surya.schema import TaskNames
            from surya.settings import settings
        except ImportError as exc:
            raise RuntimeError(
                "Surya OCR のモジュールが見つかりません。\n\n"
                "pip install surya-ocr を実行してインストールしてください。"
            ) from exc

        ocr_foundation = FoundationPredictor()
        det_predictor = DetectionPredictor()
        rec_predictor = RecognitionPredictor(ocr_foundation)

        layout_foundation = FoundationPredictor(
            checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        layout_predictor = LayoutPredictor(layout_foundation)
        table_rec_predictor = TableRecPredictor()

        return {
            "det_predictor": det_predictor,
            "rec_predictor": rec_predictor,
            "layout_predictor": layout_predictor,
            "table_rec_predictor": table_rec_predictor,
            "task_name": TaskNames.ocr_with_boxes,
        }

    def _run_surya_ocr(self, pdf_path):
        try:
            if self._surya_engine is None:
                self._start_elapsed_status("Surya OCR 初期化中")
                self._surya_engine = self._init_surya_engine()
                self._stop_elapsed_status()

            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(pdf_path)
            total = len(pdf)

            lines = []
            self._start_elapsed_status(f"Surya OCR 処理中 {total}ページ")
            try:
                for i in range(total):
                    if self._cancel_flag:
                        lines.append("\n（ユーザーによりキャンセルされました）")
                        break

                    self._set_elapsed_phase(
                        f"Surya OCR 処理中 {i + 1}/{total}", done_pages=i)

                    bitmap = pil_img = predictions = layout_preds = None
                    try:
                        page = pdf[i]
                        bitmap = page.render(scale=300 / 72)
                        pil_img = bitmap.to_pil().convert("RGB")

                        predictions = self._surya_engine["rec_predictor"](
                            [pil_img],
                            task_names=[self._surya_engine["task_name"]],
                            det_predictor=self._surya_engine["det_predictor"],
                        )

                        self._add_page_separator(lines, i + 1, total)

                        if predictions and predictions[0].text_lines:
                            for text_line in predictions[0].text_lines:
                                if text_line.text and text_line.text.strip():
                                    lines.append(japanize(text_line.text))
                        else:
                            lines.append(
                                "（このページからテキストを検出できませんでした）")

                        layout_preds = self._surya_engine["layout_predictor"](
                            [pil_img])
                        if layout_preds:
                            table_imgs = []
                            for bbox in layout_preds[0].bboxes:
                                if bbox.label in ("Table", "TableOfContents"):
                                    table_imgs.append(pil_img.crop(bbox.bbox))
                            if table_imgs:
                                table_results = self._surya_engine[
                                    "table_rec_predictor"](table_imgs)
                                for tr in table_results:
                                    table_text = self._table_to_markdown(tr)
                                    if table_text:
                                        lines.append("")
                                        lines.append("【表】")
                                        lines.append(table_text)
                                        lines.append("")
                        lines.append("")
                    except Exception as page_err:
                        self._add_page_separator(lines, i + 1, total)
                        lines.append(
                            f"（ページ {i + 1} でエラー: {page_err}）")
                        lines.append("")
                    finally:
                        if bitmap is not None:
                            del bitmap, pil_img, predictions, layout_preds

                    self._set_elapsed_phase(
                        f"Surya OCR 処理中 {i + 1}/{total}", done_pages=i + 1)
            finally:
                pdf.close()

            self._stop_elapsed_status()
            self.ocr_result = "\n".join(lines)
            self._show_result(self.ocr_result)
            if not self._cancel_flag:
                self._status(f"完了！ Surya OCR で {total} ページを処理しました。")

        except ImportError as exc:
            self._stop_elapsed_status()
            self._show_error(
                f"Surya OCR 用のモジュールが見つかりません:\n{exc}\n\n"
                "pip install surya-ocr を実行してインストールしてください。")
            self._status("エラー: モジュールが不足しています")
        except RuntimeError as exc:
            self._stop_elapsed_status()
            self._show_error(f"Surya OCR 処理中にエラーが発生しました:\n\n{exc}")
            self._status("エラーが発生しました")
        except Exception:
            self._stop_elapsed_status()
            err = traceback.format_exc()
            self._show_error(f"Surya OCR 処理中にエラーが発生しました:\n\n{err}")
            self._status("エラーが発生しました")
        finally:
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

    def _table_to_markdown(self, table_result):
        cells = table_result.cells
        if not cells:
            return ""

        grid = {}
        max_col = 0
        for cell in cells:
            row_id = cell.row_id
            col_id = cell.col_id or 0
            grid.setdefault(row_id, {}).setdefault(col_id, []).append(cell)
            max_col = max(max_col, col_id + 1)

        if max_col == 0:
            return ""

        sorted_row_ids = sorted(grid.keys())
        md_lines = []
        for row_id in sorted_row_ids:
            row_cells = []
            for col_id in range(max_col):
                cell_texts = []
                if row_id in grid and col_id in grid[row_id]:
                    for cell in grid[row_id][col_id]:
                        if cell.text_lines:
                            for tl in cell.text_lines:
                                text = tl.get("text", "") if isinstance(tl, dict) else getattr(tl, "text", "")
                                if text:
                                    cell_texts.append(text)
                row_cells.append(" ".join(cell_texts).replace("\n", " "))
            md_lines.append("| " + " | ".join(row_cells) + " |")

        if len(md_lines) > 1:
            separator = "|" + "|".join(["---" for _ in range(max_col)]) + "|"
            md_lines.insert(1, separator)

        return "\n".join(md_lines)

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
