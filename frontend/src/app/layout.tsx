import type { Metadata } from 'next';
import { Sidebar } from '@/components/layout';
import './globals.css';

export const metadata: Metadata = {
  title: 'Publishing Service Dashboard',
  description: 'Neo-brutalist dashboard for managing blogs, articles, and publishing pipelines',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="bg-panel text-base font-sans antialiased">
        <Sidebar />
        <main className="ml-[300px] min-h-screen bg-grid-pattern">
          {children}
        </main>
      </body>
    </html>
  );
}
