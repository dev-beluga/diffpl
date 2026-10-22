"use client";

import { useEffect, useState } from "react";
import { getJson } from "./api";

export type Loadable<T> = { status: "loading" } | { status: "error"; message: string } | { status: "ok"; data: T };

// Fetch a JSON endpoint once per path; aborts when the path changes or the page unmounts.
export function useApi<T>(path: string): Loadable<T> {
  const [state, setState] = useState<Loadable<T>>({ status: "loading" });
  useEffect(() => {
    const ctrl = new AbortController();
    setState({ status: "loading" });
    getJson<T>(path, ctrl.signal)
      .then((data) => setState({ status: "ok", data }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setState({ status: "error", message: e.message });
      });
    return () => ctrl.abort();
  }, [path]);
  return state;
}
