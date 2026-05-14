/**
 * #619 / #614 — Tauri command の `Result<T, AppError>` で frontend 側に届く
 * structured error の narrowing / 正規化ユーティリティ。
 *
 * Tauri は Rust 側の `error::AppError` (`gui/src-tauri/src/error.rs`) を
 * `serde::Serialize` 経由で JSON object として frontend に渡す。invoke 失敗時
 * の Promise reject value はその object そのもの:
 *
 *   { code: "io.file_not_found", message: "...", hint?: "...", stacktrace?: "..." }
 *
 * catch path では `toErrorState(e)` の 1 呼び出しで structured AppError /
 * legacy raw String / Error instance / null / undefined を統一的に扱える。
 *
 * export 一覧:
 * - AppError interface
 * - ErrorState interface
 * - isAppError type guard
 * - appErrorCodeIs predicate (catch path の code 分岐用)
 * - toErrorState normalizer (#694 Lane V Phase 2)
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
 * AppError の `code` が `expected` と一致するかを判定。
 * legacy raw String や非 AppError では false (= 「該当 code ではない」) を返すので
 * 安全に分岐に使える。
 */
export function appErrorCodeIs(e: unknown, expected: string): boolean {
  return isAppError(e) && e.code === expected;
}

/**
 * Store の inline error slot に詰める正規化済み構造。AppError と異なり:
 * - `hint` / `code` は legacy raw String や `Error` instance では `null`
 * - `stacktrace` は inline UI 用途では運ばない (ErrorModal 等の別経路で扱う)
 *
 * #694 で導入 (Lane V Phase 2)。catch path で
 * `set({ loadErrorState: toErrorState(e) })` の 1 行に短縮するための型。
 */
export interface ErrorState {
  message: string;
  hint: string | null;
  code: string | null;
}

/**
 * invoke の reject value (AppError / Error / raw String / null/undefined) を
 * ErrorState に正規化する。
 *
 * - AppError → `{ message, hint: hint ?? null, code }`
 * - Error instance → `{ message: e.message, hint: null, code: null }`
 * - その他 (raw String / null / undefined) → `{ message: String(e), hint: null, code: null }`
 */
export function toErrorState(e: unknown): ErrorState {
  if (isAppError(e)) {
    return {
      message: e.message,
      hint: typeof e.hint === 'string' ? e.hint : null,
      code: e.code,
    };
  }
  if (e instanceof Error) {
    return { message: e.message, hint: null, code: null };
  }
  return { message: String(e), hint: null, code: null };
}
