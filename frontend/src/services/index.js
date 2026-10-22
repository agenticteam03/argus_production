// The single swap point between the mock adapters and the real HTTP ones.
// Mock is the default so the offline demo and the unit tests work with no server; set VITE_ARGUS_MOCK=0
// (see .env.example and README.md) to connect to the real API through the dev proxy.
// Runbooks: the repository's library in mock mode; in real mode the edge serves them after login (ACR-0011).
import { fileRunbooksAdapter } from "./fileRunbooksAdapter.js";
import { httpArgusAdapter } from "./httpArgusAdapter.js";
import { httpAuthAdapter } from "./httpAuthAdapter.js";
import { httpRunbooksAdapter } from "./httpRunbooksAdapter.js";
import { mockArgusAdapter } from "./mockArgusAdapter.js";
import { mockAuthAdapter } from "./mockAuthAdapter.js";
import { httpSecondFactorAdapter, mockSecondFactorAdapter } from "./secondFactorAdapter.js";

const USE_MOCK = import.meta.env.VITE_ARGUS_MOCK !== "0";

// "demo" while the mock adapters are in use, "api" when talking to the real Argus API. The "Live" pill
// shows this, so demo data is never mistaken for a live deployment.
export const dataSource = USE_MOCK ? "demo" : "api";

export const auth = USE_MOCK ? mockAuthAdapter : httpAuthAdapter;
export const argus = USE_MOCK ? mockArgusAdapter : httpArgusAdapter;
export const runbooks = USE_MOCK ? fileRunbooksAdapter : httpRunbooksAdapter;
export const secondFactor = USE_MOCK ? mockSecondFactorAdapter : httpSecondFactorAdapter;   // ACR-0018 step 3
