---
title: Auto-Update
---

# Auto-Update

Greeting Cards uses the [Sparkle](https://sparkle-project.org) framework to keep itself up to date — the same updater trusted by apps like Firefox, VLC, and iTerm.

## How It Works

The app periodically checks for new versions in the background. When an update is available, a native macOS prompt appears with release notes and a one-click **Install Update** button. The app downloads the new version, quits, installs, and relaunches automatically.

## First-Launch Opt-In

The first time you open a new install, Greeting Cards asks whether you'd like to enable automatic update checks. You can change this choice later in **Settings** &rsaquo; **General** &rsaquo; **Automatically check for updates**.

## Manual Check

Choose **File** &rsaquo; **Check for Updates** to check immediately, regardless of the automatic setting.

## Settings

Open **Settings** &rsaquo; **General** to toggle **Automatically check for updates** on or off.

## Security

Updates are delivered as signed DMGs from GitHub Releases. Each update is verified with an EdDSA cryptographic signature before installation — only authentic releases from the project are accepted.
