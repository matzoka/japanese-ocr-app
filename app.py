# ============================================================
#  日本語OCRアプリ
#  エンジン: RapidOCR / Mistral OCR / Surya OCR
#  対応: 日本語 / 英語 / 数字 混在PDF
# ============================================================

import base64
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import traceback
from tkinter import ttk

import customtkinter as ctk

from database import init_db, upsert_record, search_records, get_record, delete_record
from japanize import japanize
from version import VERSION, DATE

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_HERE, "config.json")


class OCRApp:
    ENGINE_RAPID = "RapidOCR（ローカル・無料）"
    ENGINE_MISTRAL = "Mistral OCR（API・高精度）"
    ENGINE_SURYA = "Surya OCR（無料・高品質）"

    _ENGINE_VALUES = (ENGINE_RAPID, ENGINE_MISTRAL, ENGINE_SURYA)

    # 近未来的サイバーダークカラーパレット
    COLOR_BG         = "#0f172a"  # Slate 900
    COLOR_PANEL      = "#1e293b"  # Slate 800
    COLOR_ACCENT     = "#10b981"  # Emerald 500 (ネオングリーン)
    COLOR_BTN_BLUE   = "#0284c7"  # Sky 600
    COLOR_BTN_PURPLE = "#7c3aed"  # Violet 600
    COLOR_BTN_GRAY   = "#475569"  # Slate 600
    COLOR_BTN_RED    = "#ef4444"  # Red 500
    COLOR_TEXT       = "#f1f5f9"  # Slate 100
    COLOR_BORDER     = "#334155"  # Slate 700
    
    FONT_JA          = "Yu Gothic UI"

    TEXT_LAYER_MIN_LENGTH = 40
    TEXT_LAYER_MIN_PAGE_CHARS = 60

    def __init__(self, root: ctk.CTk):
        init_db()
        self.root = root
        
        # テーマ設定
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self._saved_engine = self._load_engine_config()
        self.root.title(f"Japanese OCR App  v{VERSION} ({DATE})")
        self.root.geometry("900x780")
        self.root.minsize(750, 600)
        self.root.configure(fg_color=self.COLOR_BG)

        self.ocr_result = ""
        self._rapid_engine = None
        self._surya_engine = None
        self._api_style = None
        self._cancel_flag = False
        self._elapsed_status_active = False
        self._elapsed_started_at = None
        self._elapsed_phase = ""
        self._elapsed_done_pages = 0
        self._last_ocr_info = None
        self._current_engine = ""
        self._build_ui()
        self._setup_icon()

    # ── UI ───────────────────────────────────────────────────
    def _build_ui(self):
        hdr = ctk.CTkFrame(self.root, fg_color=self.COLOR_PANEL, corner_radius=12, border_color=self.COLOR_BORDER, border_width=1)
        hdr.pack(fill=tk.X, padx=16, pady=(16, 8))
        
        ctk.CTkLabel(hdr, text="日本語 OCR アプリ",
                     font=(self.FONT_JA, 20, "bold"),
                     text_color=self.COLOR_ACCENT).pack(pady=(12, 4))
        ctk.CTkLabel(hdr, text="日本語・英語・数字の混在 PDF に対応  |  RapidOCR / Mistral OCR / Surya OCR",
                     font=(self.FONT_JA, 12),
                     text_color="#94a3b8").pack()
        ctk.CTkLabel(hdr, text=f"Version {VERSION}  （{DATE}）",
                     font=(self.FONT_JA, 10, "bold"),
                     text_color=self.COLOR_ACCENT).pack(pady=(4, 12))

        config_frame = ctk.CTkFrame(self.root, fg_color=self.COLOR_PANEL, corner_radius=12, border_color=self.COLOR_BORDER, border_width=1)
        config_frame.pack(fill=tk.X, padx=16, pady=8)

        self._build_row(config_frame, "PDF ファイル", "file")
        self._build_row(config_frame, "テキスト保存先フォルダ", "output")
        self._build_engine_row(config_frame)
        self._build_api_key_row(config_frame)

        btn_row = ctk.CTkFrame(self.root, fg_color="transparent")
        btn_row.pack(pady=12)
        
        self.ocr_btn = self._btn(btn_row, "OCR 開始",
                                  self.COLOR_ACCENT, self.start_ocr, bold=True, text_color="#0f172a")
        self.ocr_btn.pack(side=tk.LEFT, padx=6)

        self.cancel_btn = self._btn(btn_row, "キャンセル",
                                     self.COLOR_BTN_RED, self._cancel_ocr)
        self.cancel_btn.configure(state="disabled")
        self.cancel_btn.pack(side=tk.LEFT, padx=6)

        self.save_btn = self._btn(btn_row, "テキスト保存",
                                   self.COLOR_BTN_PURPLE, self.save_result)
        self.save_btn.configure(state="disabled")
        self.save_btn.pack(side=tk.LEFT, padx=6)

        self._btn(btn_row, "クリア",
                   self.COLOR_BTN_GRAY, self.clear_all).pack(side=tk.LEFT, padx=6)

        self._btn(btn_row, "DB 閲覧",
                   self.COLOR_BTN_PURPLE, self._open_db_viewer).pack(side=tk.LEFT, padx=6)

        sf = ctk.CTkFrame(self.root, fg_color="transparent")
        sf.pack(fill=tk.X, padx=20, pady=(0, 6))
        
        self.status_var = tk.StringVar(value="ファイルを選択して OCR 開始を押してください")
        ctk.CTkLabel(sf, textvariable=self.status_var,
                     font=(self.FONT_JA, 12), text_color="#94a3b8",
                     anchor="w").pack(fill=tk.X, pady=(0, 4))

        self.progress = ctk.CTkProgressBar(sf,
                                           progress_color=self.COLOR_ACCENT,
                                           fg_color=self.COLOR_BORDER,
                                           height=8,
                                           mode="indeterminate")
        self.progress.pack(fill=tk.X)
        self.progress.set(0)

        rf = ctk.CTkFrame(self.root, fg_color=self.COLOR_PANEL, corner_radius=12, border_color=self.COLOR_BORDER, border_width=1)
        rf.pack(fill=tk.BOTH, expand=True, padx=16, pady=(8, 16))
        
        ctk.CTkLabel(rf, text="  OCR 結果  ",
                     font=(self.FONT_JA, 13, "bold"),
                     text_color=self.COLOR_TEXT).pack(anchor="w", padx=16, pady=(10, 4))

        self.result_text = ctk.CTkTextbox(
            rf, font=(self.FONT_JA, 14), wrap=tk.WORD,
            fg_color="#0f172a", text_color=self.COLOR_TEXT,
            border_color=self.COLOR_BORDER, border_width=1,
            corner_radius=8
        )
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.result_text.configure(state="disabled")

    def _build_row(self, parent, label, key):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill=tk.X, padx=16, pady=8)
        
        ctk.CTkLabel(f, text=label,
                     font=(self.FONT_JA, 12, "bold"),
                     text_color="#94a3b8", width=150,
                     anchor="w").pack(side=tk.LEFT)
                     
        var = tk.StringVar()
        setattr(self, f"{key}_var", var)
        
        entry = ctk.CTkEntry(f, textvariable=var,
                             font=(self.FONT_JA, 13),
                             fg_color="#0f172a", text_color=self.COLOR_TEXT,
                             border_color=self.COLOR_BORDER,
                             height=32, corner_radius=6)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        cmd = self.browse_file if key == "file" else self.browse_output
        self._btn(f, "参照...", self.COLOR_BTN_BLUE, cmd, height=32).pack(side=tk.RIGHT)

    def _build_engine_row(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill=tk.X, padx=16, pady=8)
        
        ctk.CTkLabel(f, text="OCR エンジン",
                     font=(self.FONT_JA, 12, "bold"),
                     text_color="#94a3b8", width=150,
                     anchor="w").pack(side=tk.LEFT)

        self.engine_var = tk.StringVar(value=self._saved_engine)
        
        self.engine_combo = ctk.CTkOptionMenu(
            f,
            variable=self.engine_var,
            values=self._ENGINE_VALUES,
            command=self._on_engine_changed,
            font=(self.FONT_JA, 13),
            dropdown_font=(self.FONT_JA, 13),
            fg_color=self.COLOR_BORDER,
            button_color=self.COLOR_BORDER,
            button_hover_color=self.COLOR_BTN_BLUE,
            dropdown_fg_color=self.COLOR_PANEL,
            dropdown_hover_color=self.COLOR_BTN_BLUE,
            dropdown_text_color=self.COLOR_TEXT,
            height=32, corner_radius=6
        )
        self.engine_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _build_api_key_row(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill=tk.X, padx=16, pady=(8, 12))
        
        ctk.CTkLabel(f, text="Mistral API キー",
                     font=(self.FONT_JA, 12, "bold"),
                     text_color="#94a3b8", width=150,
                     anchor="w").pack(side=tk.LEFT)
                     
        self.api_key_var = tk.StringVar(value=os.environ.get("MISTRAL_API_KEY", ""))
        
        self._api_key_entry = ctk.CTkEntry(
            f, textvariable=self.api_key_var,
            font=(self.FONT_JA, 13), show="*",
            fg_color="#0f172a", text_color=self.COLOR_TEXT,
            border_color=self.COLOR_BORDER,
            height=32, corner_radius=6)
        self._api_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self._show_key = tk.BooleanVar(value=False)
        chk = ctk.CTkCheckBox(f, text="表示", variable=self._show_key,
                               command=self._toggle_api_key_visibility,
                               font=(self.FONT_JA, 12),
                               text_color="#94a3b8",
                               fg_color=self.COLOR_ACCENT,
                               border_color=self.COLOR_BORDER,
                               checkmark_color="#0f172a",
                               width=60)
        chk.pack(side=tk.RIGHT)

    def _toggle_api_key_visibility(self):
        self._api_key_entry.configure(
            show="" if self._show_key.get() else "*")

    def _load_engine_config(self):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                engine = json.load(f).get("engine", "")
            if engine in self._ENGINE_VALUES:
                return engine
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return self.ENGINE_RAPID

    def _save_engine_config(self):
        try:
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({"engine": self.engine_var.get()}, f, ensure_ascii=False)
        except OSError:
            pass

    def _on_engine_changed(self, _event=None):
        self._save_engine_config()

    def _btn(self, parent, text, color, cmd, bold=False, text_color="white", height=36):
        if color == self.COLOR_ACCENT:
            hover = "#34d399"
        elif color == self.COLOR_BTN_BLUE:
            hover = "#0ea5e9"
        elif color == self.COLOR_BTN_PURPLE:
            hover = "#8b5cf6"
        elif color == self.COLOR_BTN_RED:
            hover = "#f87171"
        else:
            hover = "#64748b"
            
        return ctk.CTkButton(
            parent, text=text, command=cmd,
            font=(self.FONT_JA, 13, "bold" if bold else "normal"),
            fg_color=color, text_color=text_color,
            hover_color=hover, height=height, corner_radius=8,
            border_width=0
        )

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
        self.ocr_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.save_btn.configure(state="disabled")
        self.engine_combo.configure(state="disabled")
        self._clear_result()
        self.progress.start()
        threading.Thread(target=self._run_ocr,
                          args=(pdf_path, engine_name), daemon=True).start()

    def _cancel_ocr(self):
        self._cancel_flag = True
        self.cancel_btn.configure(state="disabled")
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
        self._current_engine = engine_name
        if engine_name == self.ENGINE_MISTRAL:
            self._run_mistral_ocr(pdf_path)
        elif engine_name == self.ENGINE_SURYA:
            self._run_surya_ocr(pdf_path)
        else:
            self._run_rapid_ocr(pdf_path)

    def _run_rapid_ocr(self, pdf_path):
        pdf = None
        try:
            self._start_elapsed_status("PDF 読み込み中")
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(pdf_path)
            total = len(pdf)
            self._stop_elapsed_status()

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

            self.ocr_result = "\n".join(lines)
            self._show_result(self.ocr_result)
            if not self._cancel_flag:
                self._status(f"完了！ {total} ページを処理しました。")
                self._set_last_ocr_info(pdf_path, total)

        except ImportError as exc:
            self._show_error(
                f"必要なモジュールが見つかりません:\n{exc}\n\n"
                "setup.bat を実行してインストールしてください。")
            self._status("エラー: モジュールが不足しています")
        except Exception:
            err = traceback.format_exc()
            self._show_error(f"OCR 処理中にエラーが発生しました:\n\n{err}")
            self._status("エラーが発生しました")
        finally:
            self._stop_elapsed_status()
            if pdf is not None:
                try:
                    pdf.close()
                except Exception:
                    pass
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

            text_page = None
            try:
                page = pdf[i]
                text_page = page.get_textpage()
                text = text_page.get_text_range()
            except Exception:
                text = ""
            finally:
                if text_page is not None:
                    try:
                        text_page.close()
                    except Exception:
                        pass

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
        pdf = None
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

                    text_lines = predictions[0].text_lines if predictions else []

                    self._add_page_separator(lines, i + 1, total)

                    if text_lines:
                        for text_line in text_lines:
                            if text_line.text and text_line.text.strip():
                                lines.append(japanize(text_line.text))
                    else:
                        lines.append(
                            "（このページからテキストを検出できませんでした）")

                    layout_preds = self._surya_engine["layout_predictor"](
                        [pil_img])
                    if layout_preds:
                        for lb in layout_preds[0].bboxes:
                            if lb.label in ("Table", "TableOfContents"):
                                table_bbox = list(lb.bbox)
                                table_img = pil_img.crop(table_bbox)
                                table_results = self._surya_engine[
                                    "table_rec_predictor"]([table_img])
                                for tr in table_results:
                                    table_text = self._table_to_markdown(
                                        tr, text_lines, table_bbox)
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

            self._stop_elapsed_status()
            self.ocr_result = "\n".join(lines)
            self._show_result(self.ocr_result)
            if not self._cancel_flag:
                self._status(f"完了！ Surya OCR で {total} ページを処理しました。")
                self._set_last_ocr_info(pdf_path, total)

        except ImportError as exc:
            self._show_error(
                f"Surya OCR 用のモジュールが見つかりません:\n{exc}\n\n"
                "pip install surya-ocr を実行してインストールしてください。")
            self._status("エラー: モジュールが不足しています")
        except RuntimeError as exc:
            self._show_error(f"Surya OCR 処理中にエラーが発生しました:\n\n{exc}")
            self._status("エラーが発生しました")
        except Exception:
            err = traceback.format_exc()
            self._show_error(f"Surya OCR 処理中にエラーが発生しました:\n\n{err}")
            self._status("エラーが発生しました")
        finally:
            self._stop_elapsed_status()
            if pdf is not None:
                try:
                    pdf.close()
                except Exception:
                    pass
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
                self._set_last_ocr_info(pdf_path, total)

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

    def _table_to_markdown(self, table_result, text_lines, table_bbox):
        from surya.common.polygon import PolygonBox

        cells = table_result.cells
        if not cells:
            return ""

        cell_texts = {}
        for cell in cells:
            shifted_polygon = [
                [p[0] + table_bbox[0], p[1] + table_bbox[1]]
                for p in cell.polygon
            ]
            cell_in_page = PolygonBox(polygon=shifted_polygon)

            matched = []
            for tl in text_lines:
                if tl.intersection_pct(cell_in_page) > 0.5:
                    if tl.text and tl.text.strip():
                        matched.append(tl.text)
            cell_texts[(cell.row_id, cell.col_id or 0)] = matched

        grid = {}
        max_col = 0
        for cell in cells:
            row_id = cell.row_id
            col_id = cell.col_id or 0
            key = (row_id, col_id)
            text = " ".join(cell_texts.get(key, []))
            grid.setdefault(row_id, {})[col_id] = text
            max_col = max(max_col, col_id + 1)

        if max_col == 0:
            return ""

        sorted_rows = sorted(grid.keys())
        md_lines = []
        for row_id in sorted_rows:
            row_cells = []
            for col_id in range(max_col):
                row_cells.append(grid.get(row_id, {}).get(col_id, ""))
            md_lines.append("| " + " | ".join(row_cells) + " |")

        if len(md_lines) > 1:
            separator = "|" + "|".join(["---" for _ in range(max_col)]) + "|"
            md_lines.insert(1, separator)

        return "\n".join(md_lines)

    def _start_elapsed_status(self, phase):
        def _start():
            self._elapsed_status_active = True
            self._elapsed_started_at = time.monotonic()
            self._elapsed_phase = phase
            self._elapsed_done_pages = 0
            self._tick_elapsed_status()
        self.root.after(0, _start)

    def _set_elapsed_phase(self, phase, done_pages=None):
        self._elapsed_phase = phase
        if done_pages is not None:
            self._elapsed_done_pages = done_pages

    def _stop_elapsed_status(self):
        def _stop():
            self._elapsed_status_active = False
        self.root.after(0, _stop)

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
        self.progress.set(0)
        self.ocr_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.engine_combo.configure(state="normal")
        if self.ocr_result.strip():
            self.save_btn.configure(state="normal")
            self._save_to_db()

    # ── 保存 ─────────────────────────────────────────────────
    def save_result(self):
        if not self.ocr_result:
            return
        out_dir = self.output_var.get().strip() or os.path.expanduser("~")
        file_path = self.file_var.get().strip()
        if file_path:
            base = os.path.splitext(os.path.basename(file_path))[0]
        else:
            base = "ocr_result"
        save_path = filedialog.asksaveasfilename(
            initialdir=out_dir,
            initialfile=f"{base}_ocr.txt",
            title="テキストを保存",
            defaultextension=".txt",
            filetypes=[("テキストファイル", "*.txt"), ("すべてのファイル", "*.*")])
        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(self.ocr_result)
                messagebox.showinfo("保存完了", f"保存しました:\n{save_path}")
            except Exception as e:
                messagebox.showerror("保存エラー", f"ファイルの保存に失敗しました:\n{e}")

    # ── クリア ───────────────────────────────────────────────
    def clear_all(self):
        self._cancel_flag = True
        self._last_ocr_info = None
        self.file_var.set("")
        self.output_var.set("")
        self._clear_result()
        self.ocr_result = ""
        self.save_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        self.status_var.set("ファイルを選択して OCR 開始を押してください")

    # ── ユーティリティ ───────────────────────────────────────
    def _status(self, msg):
        self.root.after(0, lambda: self.status_var.set(msg))

    def _setup_icon(self):
        icon_ico_path = os.path.join(_HERE, "icon.ico")
        if os.path.exists(icon_ico_path):
            try:
                self.root.iconbitmap(icon_ico_path)
            except Exception:
                pass

    def _clear_result(self):
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", tk.END)
        self.result_text.configure(state="disabled")

    # ── DB 登録 ─────────────────────────────────────────────
    def _set_last_ocr_info(self, pdf_path, total):
        self._last_ocr_info = {
            "title": os.path.basename(pdf_path),
            "ocr_type": self._current_engine,
            "pages": total,
            "source_path": pdf_path,
        }

    def _save_to_db(self):
        if not self._last_ocr_info:
            return
        info = self._last_ocr_info
        now = datetime.now()
        try:
            upsert_record(
                title=info["title"],
                ocr_type=info["ocr_type"],
                pages=info["pages"],
                source_path=info["source_path"],
                ocr_text=self.ocr_result,
                created_date=now.strftime("%Y-%m-%d"),
                created_time=now.strftime("%H:%M:%S"),
            )
        except Exception:
            pass

    # ── DB 閲覧画面 ─────────────────────────────────────────
    def _open_db_viewer(self):
        win = ctk.CTkToplevel(self.root)
        win.title("OCR 履歴 DB 閲覧")
        win.geometry("950x700")
        win.minsize(750, 500)
        win.configure(fg_color=self.COLOR_BG)
        win.transient(self.root)
        win.grab_set()

        icon_ico_path = os.path.join(_HERE, "icon.ico")
        if os.path.exists(icon_ico_path):
            try:
                win.iconbitmap(icon_ico_path)
            except Exception:
                pass

        # 検索フレーム
        search_frm = ctk.CTkFrame(win, fg_color=self.COLOR_PANEL, corner_radius=10, border_color=self.COLOR_BORDER, border_width=1)
        search_frm.pack(fill=tk.X, padx=16, pady=12)
        
        ctk.CTkLabel(search_frm, text=" 検索ワード:",
                     font=(self.FONT_JA, 12, "bold"),
                     text_color="#94a3b8").pack(side=tk.LEFT, padx=(12, 6), pady=10)
                     
        search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(search_frm, textvariable=search_var,
                                    font=(self.FONT_JA, 13),
                                    fg_color="#0f172a", text_color=self.COLOR_TEXT,
                                    border_color=self.COLOR_BORDER,
                                    height=32, corner_radius=6)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        search_entry.bind("<Return>", lambda e: self._db_search(
            win, search_var.get(), tree, detail_text, status_var))
            
        self._btn(search_frm, "検索", self.COLOR_BTN_BLUE,
                  lambda: self._db_search(
                      win, search_var.get(), tree, detail_text, status_var),
                  height=32).pack(side=tk.LEFT, padx=3)
                  
        self._btn(search_frm, "全件", self.COLOR_BTN_GRAY,
                  lambda: self._db_search(
                      win, "", tree, detail_text, status_var),
                  height=32).pack(side=tk.LEFT, padx=3)

        # テーブルフレーム
        tree_frm = ctk.CTkFrame(win, fg_color=self.COLOR_PANEL, corner_radius=10, border_color=self.COLOR_BORDER, border_width=1)
        tree_frm.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        
        columns = ("id", "date", "title", "ocr_type", "pages")
        tree = ttk.Treeview(tree_frm, columns=columns, show="headings",
                            selectmode="browse")
        tree.heading("id", text="ID")
        tree.heading("date", text="登録日")
        tree.heading("title", text="タイトル")
        tree.heading("ocr_type", text="OCR種別")
        tree.heading("pages", text="頁数")
        tree.column("id", width=40, anchor=tk.CENTER)
        tree.column("date", width=100, anchor=tk.CENTER)
        tree.column("title", width=220)
        tree.column("ocr_type", width=210)
        tree.column("pages", width=50, anchor=tk.CENTER)

        # Treeviewのスタイリング (ダークテーマに合わせる)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background="#0f172a",
                        foreground=self.COLOR_TEXT,
                        fieldbackground="#0f172a",
                        bordercolor=self.COLOR_BORDER,
                        borderwidth=0,
                        rowheight=26,
                        font=(self.FONT_JA, 10))
        style.configure("Treeview.Heading",
                        font=(self.FONT_JA, 10, "bold"),
                        background=self.COLOR_PANEL,
                        foreground=self.COLOR_TEXT,
                        bordercolor=self.COLOR_BORDER,
                        borderwidth=1)
        style.map("Treeview", background=[("selected", self.COLOR_BTN_BLUE)], foreground=[("selected", "white")])

        vsb = ttk.Scrollbar(tree_frm, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)

        # 詳細表示エリア (ctk.CTkTextbox)
        detail_frm = ctk.CTkFrame(win, fg_color=self.COLOR_PANEL, corner_radius=10, border_color=self.COLOR_BORDER, border_width=1)
        detail_frm.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        
        ctk.CTkLabel(detail_frm, text="  詳細表示  ",
                     font=(self.FONT_JA, 12, "bold"),
                     text_color=self.COLOR_TEXT).pack(anchor="w", padx=16, pady=(6, 2))
                     
        detail_text = ctk.CTkTextbox(
            detail_frm, font=(self.FONT_JA, 13), wrap=tk.WORD,
            fg_color="#0f172a", text_color=self.COLOR_TEXT,
            border_color=self.COLOR_BORDER, border_width=1,
            corner_radius=8
        )
        detail_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        detail_text.configure(state="disabled")

        status_var = tk.StringVar(value="")
        ctk.CTkLabel(win, textvariable=status_var,
                     font=(self.FONT_JA, 11), text_color="#94a3b8",
                     anchor="w").pack(fill=tk.X, padx=20, pady=(0, 4))

        # ボタンエリア
        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(pady=12)
        
        self._btn(btn_row, "この結果を表示", self.COLOR_ACCENT,
                  lambda: self._db_load_to_main(
                      win, tree, detail_text, status_var),
                  text_color="#0f172a").pack(side=tk.LEFT, padx=6)
                  
        self._btn(btn_row, "削除", self.COLOR_BTN_RED,
                  lambda: self._db_delete(
                      win, tree, detail_text, status_var)).pack(side=tk.LEFT, padx=6)
                      
        self._btn(btn_row, "閉じる", self.COLOR_BTN_GRAY,
                  win.destroy).pack(side=tk.LEFT, padx=6)

        tree.bind("<<TreeviewSelect>>",
                  lambda e: self._db_on_select(tree, detail_text, status_var))

        self._db_search(win, "", tree, detail_text, status_var)
        search_entry.focus_set()

    def _db_search(self, win, query, tree, detail_text, status_var):
        tree.delete(*tree.get_children())
        detail_text.configure(state="normal")
        detail_text.delete("1.0", tk.END)
        detail_text.configure(state="disabled")
        try:
            records = search_records(query)
        except Exception:
            status_var.set("DB 検索中にエラーが発生しました")
            return
        for r in records:
            tree.insert("", tk.END,
                        iid=str(r["id"]),
                        values=(r["id"], r["created_date"],
                                r["title"], r["ocr_type"], r["pages"]))
        status_var.set(f"{len(records)} 件ヒット" if query else
                       f"全 {len(records)} 件")

    def _db_on_select(self, tree, detail_text, status_var):
        sel = tree.selection()
        if not sel:
            return
        record_id = int(sel[0])
        try:
            r = get_record(record_id)
        except Exception:
            return
        if not r:
            status_var.set("レコードが見つかりません")
            return
        detail_text.configure(state="normal")
        detail_text.delete("1.0", tk.END)
        detail_text.insert(tk.END, r.get("ocr_text", ""))
        detail_text.configure(state="disabled")
        status_var.set(
            f"選択中: {r['title']}  ({r['ocr_type']})  "
            f"{r['created_date']} {r['created_time']}  "
            f"{r['pages']}ページ")

    def _db_load_to_main(self, win, tree, detail_text, status_var):
        sel = tree.selection()
        if not sel:
            return
        record_id = int(sel[0])
        try:
            r = get_record(record_id)
        except Exception:
            return
        if not r:
            return
        self.ocr_result = r.get("ocr_text", "")
        self._show_result(self.ocr_result)

        source_path = r.get("source_path", "")
        if source_path:
            self.file_var.set(source_path)
            parent_dir = os.path.dirname(source_path)
            if parent_dir:
                self.output_var.set(parent_dir)
        else:
            self.file_var.set(r.get("title", ""))

        self.save_btn.configure(state="normal")
        self._status(f"DB から読み込みました: {r['title']}  ({r['ocr_type']})")
        win.destroy()

    def _db_delete(self, win, tree, detail_text, status_var):
        sel = tree.selection()
        if not sel:
            return
        if not messagebox.askyesno("確認", "このレコードを削除しますか？"):
            return
        record_id = int(sel[0])
        try:
            delete_record(record_id)
        except Exception:
            status_var.set("削除中にエラーが発生しました")
            return
        tree.delete(sel[0])
        detail_text.configure(state="normal")
        detail_text.delete("1.0", tk.END)
        detail_text.configure(state="disabled")
        status_var.set("削除しました")
        self._db_search(win, "", tree, detail_text, status_var)

    def _show_result(self, text):
        def _u():
            self.result_text.configure(state="normal")
            self.result_text.delete("1.0", tk.END)
            self.result_text.insert(tk.END, text)
            self.result_text.configure(state="disabled")
        self.root.after(0, _u)

    def _show_error(self, msg):
        self.root.after(0, lambda: messagebox.showerror("Error", msg))


# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = ctk.CTk()
    app = OCRApp(root)
    root.mainloop()
