// The single swap point between the mock adapters and the real HTTP ones.
// Mock is the default so the offline demo and the unit tests work with no server; set VITE_ARGUS_MOCK=0
// (see .env.example and README.md) to connect to the real API through the dev proxy.
// Runbooks have no API route in the contract yet, so they always read the repository's library.
import { fileRunbooksAdapter } from "./fileRunbooksAdapter.js";
import { httpArgusAdapter } from "./httpArgusAdapter.js";
import { httpAuthAdapter } from "./httpAuthAdapter.js";
import { mockArgusAdapter } from "./mockArgusAdapter.js";
import { mockAuthAdapter } from "./mockAuthAdapter.js";

const USE_MOCK = import.meta.env.VITE_ARGUS_MOCK !== "0";

export const auth = USE_MOCK ? mockAuthAdapter : httpAuthAdapter;
export const argus = USE_MOCK ? mockArgusAdapter : httpArgusAdapter;
export const runbooks = fileRunbooksAdapter;
