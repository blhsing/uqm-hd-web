import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL('https://test-officialwebsite.azurewebsites.net'),
  title: 'Star Control II｜星際控制 II',
  description: 'The complete browser port of The Ur-Quan Masters in English and Traditional Chinese.',
  openGraph: {
    title: 'Star Control II｜星際控制 II',
    description: 'The complete browser port of The Ur-Quan Masters in English and Traditional Chinese.',
    type: 'website',
    url: '/starcontrol2/',
    images: [{ url: '/starcontrol2/og.png', width: 1731, height: 909, alt: 'Star Control II' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Star Control II｜星際控制 II',
    description: 'The complete browser port of The Ur-Quan Masters in English and Traditional Chinese.',
    images: ['/starcontrol2/og.png'],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
