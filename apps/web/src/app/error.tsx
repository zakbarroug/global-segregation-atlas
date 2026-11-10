'use client';
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="fatal-error">
      <h1>L’explorateur a rencontré une erreur.</h1>
      <p>Aucune analyse n’a été enregistrée. Vous pouvez rouvrir une session.</p>
      <button onClick={reset}>Réessayer</button>
    </main>
  );
}
