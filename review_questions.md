# JARVIS Code Review Guidelines (for External Gemini UI)

今回の機能拡張（`imple_01.md` に基づく改修）において、大幅なリファクタリングとアーキテクチャの変更を実施しました。
外部レビューワーとなるAI（Gemini WebUI）には、以下のポイントを中心にコードレビューと動作確認を依頼してください。

## 1. モジュール化の妥当性確認
* **現状の構成**: 従来の単一ファイル `app.py` から、以下のようにディレクトリ分割を行いました。
  * `core/config.py`: 環境変数・システムプロンプトの集約
  * `models/schemas.py`: Pydanticを用いたAPIリクエスト/レスポンスのスキーマ定義
  * `tools/agent_tools.py`: Notion, Gmail, GitHub, Google Drive, PJSIP, Web検索 などの外部連携ツールの集約
  * `routers/chat.py`, `routers/oauth.py`: FastAPIのルーティング分割
  * `app.py`: エントリーポイント、DBプール初期化、LangGraphのステートグラフ構築
* **確認事項**:
  * 依存関係の循環（Circular Import）が発生していないか。
  * `app_graph` や `db_pool` といったグローバルな状態を `app.state` を経由してルーターに渡す実装（`routers/chat.py` 参照）が、FastAPIのベストプラクティスに沿っているか。

## 2. GitHub App認証のセキュア化・JWT生成フロー
* **現状の構成**: 
  * 従来のPAT（Personal Access Token）からGitHub App認証を優先するように `github_create_repo` ツールを書き換えました。
  * `PyJWT` を利用し、`GITHUB_APP_ID` と `GITHUB_PRIVATE_KEY_PATH` からInstallation Tokenを動的に生成するフローを `_get_github_app_token` 関数として実装しています。
* **確認事項**:
  * トークンの有効期限設定（`iat`, `exp`）やアルゴリズム（`RS256`）の実装にセキュリティ上の問題はないか。
  * `oauth_config.json` に手動で保存されたPATへフォールバックするロジックは安全かつ適切か。

## 3. LangGraph × PostgreSQL の履歴管理と消去機能
* **現状の構成**: 
  * `PostgresSaver` を利用してチャット履歴をDBに永続化しています。
  * リセット要請に対して、`/api/chat/clear` エンドポイントで直接 `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` の該当 `thread_id` レコードをDELETEする生SQLを実行する設計としました。
* **確認事項**:
  * LangGraph公式の標準メソッドに「特定スレッドの履歴全消去」が存在しないため、生SQLを発行していますが、テーブル構造（PostgresSaverのスキーマ）に対してこのDELETE文が安全に機能するか（カスケード削除の観点など含め）。

## 4. 動的モデル切り替え機能 (Dynamic LLM Instantiation)
* **現状の構成**:
  * これまでグローバルにインスタンス化していた `ChatGoogleGenerativeAI` を、リクエストごとの設定（`config["configurable"]["model_name"]`）に基づいて `call_model` ノード内で動的に生成（`bind_tools` 含む）するよう変更しました。
* **確認事項**:
  * 毎回のノード実行時にLLMインスタンスとツールのバインドを再生成するアプローチによるオーバーヘッドは許容範囲か。他に LangGraph でモデルを動的に差し替えるための推奨されるベストプラクティスがあれば教えてください。
