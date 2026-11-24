import * as vscode from 'vscode';

/**
 * Singleton Logger managing the EdgeMind OutputChannel.
 * Provides timestamped logging and output visibility management.
 */
export class Logger {
  private static instance: Logger | null = null;
  private channel: vscode.OutputChannel;

  private constructor() {
    this.channel = vscode.window.createOutputChannel('EdgeMind');
  }

  public static getInstance(): Logger {
    if (!Logger.instance) {
      Logger.instance = new Logger();
    }
    return Logger.instance;
  }

  public getChannel(): vscode.OutputChannel {
    return this.channel;
  }

  public info(message: string): void {
    const timestamp = new Date().toISOString();
    this.channel.appendLine(`[${timestamp}] [INFO] ${message}`);
  }

  public warn(message: string): void {
    const timestamp = new Date().toISOString();
    this.channel.appendLine(`[${timestamp}] [WARN] ${message}`);
  }

  public error(message: string, error?: unknown): void {
    const timestamp = new Date().toISOString();
    this.channel.appendLine(`[${timestamp}] [ERROR] ${message}`);
    if (error instanceof Error && error.stack) {
      this.channel.appendLine(error.stack);
    } else if (error) {
      this.channel.appendLine(String(error));
    }
  }

  public show(preserveFocus: boolean = true): void {
    this.channel.show(preserveFocus);
  }

  public dispose(): void {
    this.channel.dispose();
    Logger.instance = null;
  }
}
