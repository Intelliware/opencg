// Key-value store for admin UI sessions: Valkey in the stack (design D11).
import type { Redis } from "ioredis";

import { valkeyUrl } from "./config";

export interface KeyValueStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string, ttlSeconds: number): Promise<void>;
  del(key: string): Promise<void>;
}

class ValkeyStore implements KeyValueStore {
  private client: Promise<Redis> | null = null;

  private connection(): Promise<Redis> {
    if (!this.client) {
      this.client = import("ioredis").then(
        ({ Redis }) =>
          new Redis(valkeyUrl(), {
            // Fail a request fast when Valkey is down instead of queueing it.
            maxRetriesPerRequest: 1,
            connectTimeout: 5_000,
          }),
      );
    }
    return this.client;
  }

  async get(key: string): Promise<string | null> {
    return (await this.connection()).get(key);
  }

  async set(key: string, value: string, ttlSeconds: number): Promise<void> {
    await (await this.connection()).set(key, value, "EX", Math.max(1, Math.ceil(ttlSeconds)));
  }

  async del(key: string): Promise<void> {
    await (await this.connection()).del(key);
  }
}

// One client per server process; globalThis survives dev-mode module reloads.
const holder = globalThis as typeof globalThis & { __opencgSessionStore?: KeyValueStore };

export function sessionStore(): KeyValueStore {
  holder.__opencgSessionStore ??= new ValkeyStore();
  return holder.__opencgSessionStore;
}

export function setSessionStoreForTests(store: KeyValueStore | undefined): void {
  holder.__opencgSessionStore = store;
}

/** In-memory store for unit tests and Storybook-free local experiments. */
export class MemoryStore implements KeyValueStore {
  readonly data = new Map<string, { value: string; expiresAt: number }>();

  constructor(private readonly now: () => number = Date.now) {}

  async get(key: string): Promise<string | null> {
    const entry = this.data.get(key);
    if (!entry) return null;
    if (entry.expiresAt <= this.now()) {
      this.data.delete(key);
      return null;
    }
    return entry.value;
  }

  async set(key: string, value: string, ttlSeconds: number): Promise<void> {
    this.data.set(key, { value, expiresAt: this.now() + ttlSeconds * 1000 });
  }

  async del(key: string): Promise<void> {
    this.data.delete(key);
  }
}
