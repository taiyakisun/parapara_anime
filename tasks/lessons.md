# Lessons

- Windows の `.bat` を LF 改行で保存する場合、複数行にすると `cmd.exe` が行頭文字を欠落させる環境がある。LF 方針を維持する必要があるランチャーは、ASCII の1行形式にして実機の `cmd.exe` で確認する。
- `uv` で作成した `.venv` にはpipが含まれない場合がある。依存関係を追加したときは `uv pip install --python .venv\Scripts\python.exe -r requirements.txt` で既存環境にも反映し、BATと同じ仮想環境で起動確認する。
