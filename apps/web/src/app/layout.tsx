import type { Metadata } from 'next';
import 'maplibre-gl/dist/maplibre-gl.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'Global Segregation Atlas — Une autre lecture des territoires',
  description:
    'Explorez la ségrégation résidentielle avec des données officielles, des méthodes explicites et sans stockage permanent.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>
        <a href="#explorer" className="skip-link">
          Aller à l’explorateur
        </a>
        {children}
      </body>
    </html>
  );
}
