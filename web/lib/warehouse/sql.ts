// The read-only gate in front of the engine (task 42). The SQL runs on the visitor's own
// machine, but this page is not a tool for reading other origins or changing the engine: a
// statement is rejected here, before the engine is even loaded, unless it is one SELECT, WITH
// or EXPLAIN with no extension, attach, copy or settings keyword and no URL in it. The engine
// itself is locked down as well once it is ready (engine.ts: `enable_external_access = false`
// with the registered files as the only allowed paths), so what this text check cannot see
// (a URL built with `concat`) still reads nothing.
//
// The tokenizer errs on the side of rejecting: block comments do not nest and strings know
// only the `''` escape, so where it and DuckDB could disagree it sees more code, not less.

export type SqlCheck = { ok: true; tables: string[] } | { ok: false; reason: string };

type TokenKind = "word" | "identifier" | "string" | "number" | "symbol";
export interface Token {
  kind: TokenKind;
  text: string;
  at: number; // where it starts in the SQL
}

const READ_STATEMENTS = ["select", "with", "explain"];

// Statement keywords that write, load, attach, copy or configure. Rejected anywhere outside
// strings, comments and quoted identifiers (no column of the seven tables is named after one).
const DENIED_WORDS = new Set([
  "alter",
  "attach",
  "call",
  "checkpoint",
  "copy",
  "create",
  "delete",
  "detach",
  "drop",
  "execute",
  "export",
  "import",
  "insert",
  "install",
  "load",
  "pragma",
  "prepare",
  "reset",
  "set",
  "truncate",
  "update",
  "use",
  "vacuum",
]);

// Table functions that run a SQL string, which this check could not see into.
const DENIED_FUNCTIONS = new Set(["query", "query_table"]);

class SqlSyntaxError extends Error {}

const WORD = /[\p{L}_][\p{L}\p{N}_$]*/uy;
const NUMBER = /[0-9][0-9_]*(\.[0-9_]*)?([eE][+-]?[0-9]+)?/y;
const DOLLAR_TAG = /\$([A-Za-z_][A-Za-z0-9_]*)?\$/y;

function match(pattern: RegExp, sql: string, at: number): string | null {
  pattern.lastIndex = at;
  return pattern.exec(sql)?.[0] ?? null;
}

// A quoted run starting at `at`, with the quote doubled as its only escape.
function quoted(sql: string, at: number, quote: string): [string, number] {
  let text = "";
  let from = at + 1;
  for (;;) {
    const close = sql.indexOf(quote, from);
    if (close === -1) throw new SqlSyntaxError(`Unterminated ${quote === "'" ? "string" : "identifier"}.`);
    if (sql[close + 1] === quote) {
      text += sql.slice(from, close + 1);
      from = close + 2;
      continue;
    }
    return [text + sql.slice(from, close), close + 1];
  }
}

export function tokenize(sql: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  while (i < sql.length) {
    const c = sql[i];
    if (/\s/.test(c)) {
      i += 1;
    } else if (sql.startsWith("--", i)) {
      // Ends at `\r` as well as `\n`, as in DuckDB.
      const end = sql.slice(i).search(/[\r\n]/);
      i = end === -1 ? sql.length : i + end + 1;
    } else if (sql.startsWith("/*", i)) {
      // DuckDB nests block comments: `/* /* */ */` is one comment.
      let depth = 1;
      let k = i + 2;
      while (depth > 0) {
        const open = sql.indexOf("/*", k);
        const close = sql.indexOf("*/", k);
        if (close === -1) throw new SqlSyntaxError("Unterminated comment.");
        if (open !== -1 && open < close) {
          depth += 1;
          k = open + 2;
        } else {
          depth -= 1;
          k = close + 2;
        }
      }
      i = k;
    } else if (c === "'" || c === '"') {
      const [text, next] = quoted(sql, i, c);
      tokens.push({ kind: c === "'" ? "string" : "identifier", text, at: i });
      i = next;
    } else if (match(DOLLAR_TAG, sql, i) !== null) {
      const tag = match(DOLLAR_TAG, sql, i)!;
      const close = sql.indexOf(tag, i + tag.length);
      if (close === -1) throw new SqlSyntaxError("Unterminated dollar-quoted string.");
      tokens.push({ kind: "string", text: sql.slice(i + tag.length, close), at: i });
      i = close + tag.length;
    } else if (match(WORD, sql, i) !== null) {
      const word = match(WORD, sql, i)!;
      tokens.push({ kind: "word", text: word, at: i });
      i += word.length;
    } else if (match(NUMBER, sql, i) !== null) {
      const number = match(NUMBER, sql, i)!;
      tokens.push({ kind: "number", text: number, at: i });
      i += number.length;
    } else {
      tokens.push({ kind: "symbol", text: c, at: i });
      i += 1;
    }
  }
  return tokens;
}

const lower = (t: Token | undefined) => (t?.kind === "word" ? t.text.toLowerCase() : null);
const isSymbol = (t: Token | undefined, s: string) => t?.kind === "symbol" && t.text === s;

// SELECT or WITH, after any opening parentheses; EXPLAIN [ANALYZE] in front of one of those.
function startsWithRead(statement: Token[]): boolean {
  let k = 0;
  const skipParens = () => {
    while (isSymbol(statement[k], "(")) k += 1;
  };
  skipParens();
  if (lower(statement[k]) === "explain") {
    k += 1;
    if (lower(statement[k]) === "analyze") k += 1;
    skipParens();
  }
  const first = lower(statement[k]);
  return first === "select" || first === "with";
}

const reject = (reason: string): SqlCheck => ({ ok: false, reason });

// `tables` are the registered short names; the result lists the ones the statement mentions
// (as a word or a quoted identifier), so the engine creates only the views it needs.
export function checkSql(sql: string, tables: readonly string[]): SqlCheck {
  let tokens: Token[];
  try {
    tokens = tokenize(sql);
  } catch (error) {
    if (error instanceof SqlSyntaxError) return reject(error.message);
    throw error;
  }

  const statements: Token[][] = [[]];
  for (const t of tokens) {
    if (isSymbol(t, ";")) statements.push([]);
    else statements[statements.length - 1].push(t);
  }
  const nonEmpty = statements.filter((s) => s.length > 0);
  if (nonEmpty.length === 0) return reject("Nothing to run: write a SELECT, WITH or EXPLAIN.");
  if (nonEmpty.length > 1) return reject("One statement at a time.");
  const [statement] = nonEmpty;

  if (!startsWithRead(statement)) {
    return reject(`Only ${READ_STATEMENTS.map((s) => s.toUpperCase()).join(", ")} run here.`);
  }
  for (let k = 0; k < statement.length; k += 1) {
    const t = statement[k];
    const word = lower(t);
    if (word !== null && DENIED_WORDS.has(word)) {
      return reject(`${t.text.toUpperCase()} is not allowed: this page only reads.`);
    }
    if (word !== null && DENIED_FUNCTIONS.has(word) && isSymbol(statement[k + 1], "(")) {
      return reject(`${t.text}() is not allowed: it runs SQL this check cannot see.`);
    }
    if ((t.kind === "string" || t.kind === "identifier") && t.text.includes("://")) {
      return reject("No URLs: the tables are the files in warehouse.json, read by name.");
    }
  }

  const named = new Set(
    statement.filter((t) => t.kind === "word" || t.kind === "identifier").map((t) => t.text.toLowerCase()),
  );
  return { ok: true, tables: tables.filter((table) => named.has(table.toLowerCase())) };
}
