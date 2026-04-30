/**
 * #619 / #614 — Tauri command の `Result<T, AppError>` で frontend 側に届く
 * structured error の narrowing helper。
 *
 * Tauri は Rust 側の `error::AppError` (`gui/src-tauri/src/error.rs`) を
 * `serde::Serialize` 経由で JSON object として frontend に渡す。invoke 失敗時
 * の Promise reject value はその object そのもの:
 *
 *   { code: "io.file_not_found", message: "...", hint?: "...", stacktrace?: "..." }
 *
 * 旧実装は `Err("...".to_string())` で raw String を返していたため、catch ブロッ
 * クは `e instanceof Error ? e.message : String(e)` で文字列化していた。本
 * ヘルパーは structured AppError (PR #665 で全 23 commands を migration) と
 * legacy raw String の両方に対応する。
 *
 * 詳細フォーマットは `docs/tauri-commands.md` 参照。
 */

export interface AppError {
  code: string;
  message: string;
  hint?: string;
  stacktrace?: string;
}

/** invoke の reject value が AppError object かを判定する type guard。 */
export function isAppError(e: unknown): e is AppError {
  if (typeof e !== 'object' || e === null) return false;
  const obj = e as Record<string, unknown>;
  return typeof obj.code === 'string' && typeof obj.message === 'string';
}

/**
 * invoke の reject value から user-facing message を取り出す。
 * - AppError → `e.message`
 * - Error instance → `e.message`
 * - その他 (legacy raw String 等) → `String(e)`
 */
export function appErrorMessage(e: unknown): string {
  if (isAppError(e)) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}

/**
 * AppError の `code` が `expected` と一致するかを判定。
 * legacy raw String や非 AppError では false (= 「該当 code ではない」) を返すので
 * 安全に分岐に使える。
 */
export function appErrorCodeIs(e: unknown, expected: string): boolean {
  return isAppError(e) && e.code === expected;
}

/**
 * AppError の hint があれば返す。なければ null。UI で「対処ヒント」を出す
 * ときに使う想定。
 */
export function appErrorHint(e: unknown): string | null {
  return isAppError(e) && typeof e.hint === 'string' ? e.hint : null;
}
