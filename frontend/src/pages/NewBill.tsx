import { type ChangeEvent, useState } from "react";
import { ApiError, api, type Validation } from "../api";
import { go } from "../router";
import { Badge } from "../components/values";
import { EXAMPLES } from "../examples";

type Result =
  | { kind: "idle" }
  | { kind: "busy"; what: string }
  | { kind: "valid"; validation: Validation }
  | { kind: "invalid"; validation: Validation }
  | { kind: "error"; message: string };

function Errors({ validation }: { validation: Validation }) {
  return (
    <div className="alert alert-bad" role="alert">
      <strong>
        The bill is not valid: {validation.errors.length} problem
        {validation.errors.length === 1 ? "" : "s"}. Nothing was calculated or saved.
      </strong>
      <div className="table-wrap">
        <table className="table compact">
          <thead>
            <tr>
              <th>Where</th>
              <th>Problem</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {validation.errors.map((error, index) => (
              <tr key={`${error.path}-${error.code}-${index}`}>
                <td>
                  <code>{error.path}</code>
                </td>
                <td>
                  <code>{error.code}</code>
                </td>
                <td>{error.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Warnings({ validation }: { validation: Validation }) {
  return (
    <div className="alert alert-good" role="status">
      <strong>
        The bill is valid
        {validation.tariff ? ` for tariff ${validation.tariff.id}` : ""}.
      </strong>{" "}
      {validation.tariff?.status === "synthetic" && <Badge tone="synthetic">Synthetic tariff</Badge>}
      {validation.warnings.length > 0 && (
        <ul className="issues">
          {validation.warnings.map((warning, index) => (
            <li key={`${warning.code}-${index}`}>
              <Badge tone={warning.code === "input-estimated" ? "estimated" : "neutral"}>
                {warning.code}
              </Badge>{" "}
              {warning.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function NewBill() {
  const [text, setText] = useState("");
  const [source, setSource] = useState<string | null>(null);
  const [result, setResult] = useState<Result>({ kind: "idle" });
  const busy = result.kind === "busy";

  const fail = (error: unknown) => {
    if (error instanceof ApiError && error.validation) {
      setResult({ kind: "invalid", validation: error.validation });
    } else {
      setResult({
        kind: "error",
        message: error instanceof ApiError ? error.message : "Something went wrong.",
      });
    }
  };

  const load = (value: string, from: string) => {
    setText(value);
    setSource(from);
    setResult({ kind: "idle" });
  };

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) load(await file.text(), file.name);
    event.target.value = "";
  };

  const validate = async () => {
    setResult({ kind: "busy", what: "Checking the bill…" });
    try {
      const validation = await api.validate(text);
      setResult({ kind: "valid", validation });
    } catch (error) {
      fail(error);
    }
  };

  const save = async (command: "reconcile" | "calculate") => {
    setResult({
      kind: "busy",
      what: command === "reconcile" ? "Calculating and reconciling…" : "Calculating…",
    });
    try {
      const created = await api.save(text, command);
      go(`#/runs/${created.run.run_id}`);
    } catch (error) {
      fail(error);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Check a bill</h1>
          <p className="lead">
            Upload or paste a bill in SAMAY's <code>samay.bill/1</code> format: the meter readings
            and the amounts printed on the utility's bill. SAMAY validates it, recalculates every
            line from the tariff, compares each line with the printed bill and saves the result.
          </p>
        </div>
      </div>

      <div className="grid-2">
        <section className="card">
          <h2>1. Bill input</h2>
          <div className="row">
            <label className="button">
              Upload JSON file
              <input type="file" accept=".json,application/json" onChange={onFile} hidden />
            </label>
            {source && <span className="muted">Loaded: {source}</span>}
          </div>
          <label className="field-label" htmlFor="bill-text">
            Bill (samay.bill/1 JSON)
          </label>
          <textarea
            id="bill-text"
            className="code-input"
            spellCheck={false}
            value={text}
            placeholder='{"format": "samay.bill/1", ...}'
            onChange={(event) => {
              setText(event.target.value);
              setSource("edited");
              setResult({ kind: "idle" });
            }}
          />
          <div className="row actions">
            <button type="button" onClick={validate} disabled={busy || !text.trim()}>
              Validate
            </button>
            <button
              type="button"
              className="primary"
              onClick={() => save("reconcile")}
              disabled={busy || !text.trim()}
            >
              Calculate, reconcile and save
            </button>
            <button
              type="button"
              className="ghost"
              onClick={() => save("calculate")}
              disabled={busy || !text.trim()}
            >
              Calculate only
            </button>
          </div>
          {result.kind === "busy" && <p className="muted">{result.what}</p>}
          {result.kind === "valid" && <Warnings validation={result.validation} />}
          {result.kind === "invalid" && <Errors validation={result.validation} />}
          {result.kind === "error" && (
            <div className="alert alert-bad" role="alert">
              {result.message}
            </div>
          )}
        </section>

        <aside className="card">
          <h2>Sample bills</h2>
          <p className="muted small">
            Synthetic examples for the SAMAY-DEMO-1 tariff. Its rates are made up: these are not real
            UP bills.
          </p>
          <ul className="examples">
            {EXAMPLES.map((example) => (
              <li key={example.name}>
                <button type="button" className="link" onClick={() => load(example.text, `${example.name}.json`)}>
                  {example.name}.json
                </button>
                <span className="muted small">{example.description}</span>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </>
  );
}
