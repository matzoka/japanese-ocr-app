@echo off
call venv\Scripts\activate.bat
python -c "from rapidocr import LangRec, OCRVersion, RapidOCR; import importlib.util, inspect, os; print('RapidOCR signature:', inspect.signature(RapidOCR.__init__)); engine = RapidOCR(params={'Rec.lang_type': LangRec.JAPAN, 'Rec.ocr_version': OCRVersion.PPOCRV4}); print('RapidOCR language:', engine.cfg.Rec.lang_type); print('RapidOCR version:', engine.cfg.Rec.ocr_version); import mistralai; print('mistralai module: OK'); print('MISTRAL_API_KEY:', 'set' if os.environ.get('MISTRAL_API_KEY') else 'not set'); print('PaddleOCR-VL module:', 'OK' if importlib.util.find_spec('paddleocr') else 'not installed')"
pause
