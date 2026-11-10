"use client";

export interface GlobalLoadingState {
  isLoading: boolean;
  activeCount: number;
  stageMessage?: string;
  isError: boolean;
  errorMessage?: string | null;
}

type LoadingSubscriber = (state: GlobalLoadingState) => void;

class LoadingManager {
  private activeCount: number = 0;
  private stageMessage?: string;
  private isError: boolean = false;
  private errorMessage?: string | null;
  private subscribers: Set<LoadingSubscriber> = new Set();
  private errorTimeout?: ReturnType<typeof setTimeout>;

  public getState(): GlobalLoadingState {
    return {
      isLoading: this.activeCount > 0,
      activeCount: this.activeCount,
      stageMessage: this.stageMessage,
      isError: this.isError,
      errorMessage: this.errorMessage,
    };
  }

  public subscribe(callback: LoadingSubscriber): () => void {
    this.subscribers.add(callback);
    callback(this.getState());
    return () => {
      this.subscribers.delete(callback);
    };
  }

  private notify(): void {
    const state = this.getState();
    this.subscribers.forEach((cb) => {
      try {
        cb(state);
      } catch (err) {
        console.error("Error in loading subscriber:", err);
      }
    });
  }

  public startRequest(message?: string): () => void {
    this.activeCount += 1;
    if (message) {
      this.stageMessage = message;
    }
    if (this.isError) {
      this.isError = false;
      this.errorMessage = null;
    }
    this.notify();

    let finished = false;
    return () => {
      if (!finished) {
        finished = true;
        this.finishRequest();
      }
    };
  }

  public finishRequest(isError: boolean = false, errorMsg?: string): void {
    this.activeCount = Math.max(0, this.activeCount - 1);
    if (this.activeCount === 0) {
      this.stageMessage = undefined;
    }
    if (isError) {
      this.isError = true;
      this.errorMessage = errorMsg || "Request failed";
      if (this.errorTimeout) clearTimeout(this.errorTimeout);
      this.errorTimeout = setTimeout(() => {
        this.isError = false;
        this.errorMessage = null;
        this.notify();
      }, 3000);
    }
    this.notify();
  }

  public reset(): void {
    this.activeCount = 0;
    this.stageMessage = undefined;
    this.isError = false;
    this.errorMessage = null;
    if (this.errorTimeout) clearTimeout(this.errorTimeout);
    this.notify();
  }
}

export const globalLoadingManager = new LoadingManager();

