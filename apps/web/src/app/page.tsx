import Atlas from '@/components/Atlas';

export const dynamic = 'force-dynamic';
export default function Home() {
  return <Atlas styleUrl={process.env.MAP_STYLE_URL || ''} />;
}
