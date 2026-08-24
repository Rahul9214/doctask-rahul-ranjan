import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import {
  corpusDisplayName,
  corpusMetaLabel,
  corpusPrimaryLabel,
  nameCounts,
} from "./corpus";
import type { CorpusSummary, SourceSummary } from "./types";

interface CorpusSelectProps {
  id: string;
  corpora: CorpusSummary[];
  sourcesByCorpus: Record<string, SourceSummary[]>;
  value: string;
  onChange: (corpusId: string) => void;
  disabled?: boolean;
  required?: boolean;
  loading?: boolean;
}

export default function CorpusSelect({
  id,
  corpora,
  sourcesByCorpus,
  value,
  onChange,
  disabled = false,
  required = true,
  loading = false,
}: CorpusSelectProps) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const duplicates = nameCounts(corpora);
  const selected = corpora.find((corpus) => corpus.id === value);

  const options = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return corpora
      .map((corpus) => {
        const duplicate = (duplicates.get(corpusDisplayName(corpus)) ?? 0) > 1;
        return {
          corpus,
          primary: corpusPrimaryLabel(corpus, duplicate),
          meta: corpusMetaLabel(corpus, sourcesByCorpus[corpus.id]),
          duplicate,
        };
      })
      .filter((option) => {
        if (!normalized) {
          return true;
        }
        return (
          option.primary.toLowerCase().includes(normalized) ||
          option.meta.toLowerCase().includes(normalized) ||
          option.corpus.name.toLowerCase().includes(normalized)
        );
      });
  }, [corpora, duplicates, query, sourcesByCorpus]);

  useEffect(() => {
    if (!open) {
      return;
    }
    searchRef.current?.focus();
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    }
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        setQuery("");
        document.getElementById(id)?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [id, open]);

  if (corpora.length === 0 && !loading) {
    return (
      <input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        disabled={disabled}
        autoComplete="off"
      />
    );
  }

  const selectedPrimary = selected
    ? corpusPrimaryLabel(
        selected,
        (duplicates.get(corpusDisplayName(selected)) ?? 0) > 1,
      )
    : "";
  const selectedMeta = selected
    ? corpusMetaLabel(selected, sourcesByCorpus[selected.id])
    : "";

  function choose(corpusId: string) {
    onChange(corpusId);
    setOpen(false);
    setQuery("");
  }

  function onTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (
      event.key === "ArrowDown" ||
      event.key === "Enter" ||
      event.key === " "
    ) {
      event.preventDefault();
      setOpen(true);
      setActiveIndex(0);
    }
  }

  function onSearchKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) =>
        options.length === 0 ? 0 : (current + 1) % options.length,
      );
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) =>
        options.length === 0
          ? 0
          : (current - 1 + options.length) % options.length,
      );
    } else if (event.key === "Enter") {
      event.preventDefault();
      const option = options[activeIndex];
      if (option) {
        choose(option.corpus.id);
      }
    }
  }

  return (
    <div className="corpus-picker" ref={rootRef}>
      <button
        id={id}
        className="corpus-picker__trigger"
        type="button"
        disabled={disabled || loading}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-required={required || undefined}
        data-corpus-id={value}
        title={selected?.id}
        onClick={() => {
          setOpen((current) => !current);
          setQuery("");
          setActiveIndex(0);
        }}
        onKeyDown={onTriggerKeyDown}
      >
        {loading ? (
          <span className="corpus-picker__placeholder">Loading corpora…</span>
        ) : selected ? (
          <>
            <span className="corpus-picker__name">{selectedPrimary}</span>
            {selectedMeta ? (
              <span className="corpus-picker__meta">{selectedMeta}</span>
            ) : null}
          </>
        ) : (
          <span className="corpus-picker__placeholder">Select a corpus</span>
        )}
      </button>
      {open && (
        <div className="corpus-picker__popover">
          <label className="visually-hidden" htmlFor={`${id}-search`}>
            Filter corpora
          </label>
          <input
            id={`${id}-search`}
            ref={searchRef}
            className="corpus-picker__search"
            value={query}
            placeholder="Filter corpora"
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={onSearchKeyDown}
            autoComplete="off"
          />
          <ul
            id={listId}
            className="corpus-picker__list"
            role="listbox"
            aria-label="Corpora"
          >
            {options.length === 0 ? (
              <li className="corpus-picker__empty">No matching corpora</li>
            ) : (
              options.map((option, index) => (
                <li key={option.corpus.id}>
                  <button
                    className={`corpus-picker__option ${
                      option.corpus.id === value
                        ? "corpus-picker__option--selected"
                        : ""
                    } ${
                      index === activeIndex
                        ? "corpus-picker__option--active"
                        : ""
                    }`}
                    type="button"
                    role="option"
                    aria-selected={option.corpus.id === value}
                    title={option.corpus.id}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => choose(option.corpus.id)}
                  >
                    <span className="corpus-picker__name">
                      {option.primary}
                    </span>
                    {option.meta ? (
                      <span className="corpus-picker__meta">{option.meta}</span>
                    ) : null}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
