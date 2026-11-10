# Browser smoke test

Use the running application at http://127.0.0.1:3000. This test uses real, live providers and keeps the current result only in browser memory. Do not save screenshots containing live analysis data in source or fixtures.

1. Search **New York**. Verify multiple city results with country and administrative labels. Select the New York City result in the United States.
2. The map must center immediately. Verify progress from source identification through download, validation and computation.
3. Wait for **Mesuré**. Check that official polygons are actually drawn, the legend shows a local household share, and all five citywide metric cards are present. Compare the displayed coverage with the API event.
4. Switch the map indicator from low- to high-income household share. Use the accessible tract dropdown to inspect a sector. A zero-household tract must show an unavailable share, not zero percent. Other tracts must display their actual income share and Census household estimate/MOE.
5. Open the sources tab. Verify ACS and TIGERweb citations, matching vintages, retrieval timestamps and warnings. Open the export tab; both exports must be enabled only after a completed valid analysis. Downloads are deliberately user initiated.
6. Search **Vienna**, select **Vienne · Autriche**. Verify the previous map overlay and metrics clear, the map moves immediately, and an explicit `insufficient_data` explanation appears with source-attempt details. Exports must be disabled.
7. Search **Casablanca**, select the Moroccan result (not Chile or another country). Verify the same honest fallback behavior and the correct map location.
8. Start another NYC run and cancel it; verify the canceled state. Changing cities during a run must abort the prior stream and ignore its late events.
9. Test at desktop (1440 × 1000) and mobile (390 × 844) widths. Verify there is no horizontal page overflow, search remains usable, the map attribution is visible, and cards/panels stack on mobile.
10. Restore the normal viewport. Inspect browser console for application errors. Clear the session by reloading when finished; no query history or result should be restored from storage.

The browser implementation uses MapLibre 6's explicit ESM worker URL so both development and production builds can load its worker. This was caught and fixed through real browser testing, rather than relying solely on a successful TypeScript build.
