# Japanese OCR App

日本語・英語・数字の混在PDFに対応したOCRアプリです。  
RapidOCR、Mistral OCR、Surya OCR を切り替えて利用できます。

## 実行画面

### セットアップ画面

![セットアップ画面](docs/images/setup.png)

### メイン画面

![メイン画面](docs/images/main-window.png)

### DB履歴画面

![DB履歴画面](docs/images/db-history-window.png)

## 主な機能

- PDFファイルのOCR処理
- RapidOCR / Mistral OCR / Surya OCR の切り替え
- PDF内テキスト層の抽出
- OCR結果のテキスト保存
- SQLiteによるOCR履歴保存
- DB履歴画面での検索、閲覧、削除
- 中国簡体字が混入したOCR結果の日本語漢字への正規化

## セットアップ

1. Python 3.9以上をインストールします。
2. `setup.bat` を実行します。
3. セットアップ完了後、`run.bat` でアプリを起動します。

初回はOCRモデルのダウンロードが行われるため、時間がかかる場合があります。

## 使い方

1. `run.bat` を実行します。
2. 「参照...」からPDFファイルを選択します。
3. OCRエンジンを選択します。
4. Mistral OCRを使う場合はAPIキーを入力します。
5. 「OCR 開始」を押します。
6. 結果を確認し、必要に応じてテキスト保存またはDB履歴を開きます。

## OCRエンジン

### RapidOCR

ローカルで処理する無料のOCRエンジンです。PDF内にテキスト層がある場合は、画像OCRより先にテキスト層を抽出します。

### Mistral OCR

Mistral APIを使う高精度OCRです。利用にはMistral APIキーが必要です。

### Surya OCR

ローカルで処理する高品質OCRエンジンです。レイアウト検出により、表をMarkdown形式で出力できます。

## 詳細

詳しい説明は [README.txt](README.txt) を参照してください。
