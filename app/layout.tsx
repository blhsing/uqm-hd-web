import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL('https://test-officialwebsite.azurewebsites.net'),
  title: 'Star Control II — Web Edition｜星際控制 II 網頁版',
  description: 'The complete browser port of The Ur-Quan Masters HD in English and Traditional Chinese.',
  openGraph: {
    title: 'Star Control II — Web Edition｜星際控制 II 網頁版',
    description: 'The complete browser port of The Ur-Quan Masters HD in English and Traditional Chinese.',
    type: 'website',
    url: '/starcontrol2/',
    images: [{ url: '/starcontrol2/og.png', width: 1731, height: 909, alt: 'Star Control II — Web Edition' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Star Control II — Web Edition｜星際控制 II 網頁版',
    description: 'The complete browser port of The Ur-Quan Masters HD in English and Traditional Chinese.',
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
