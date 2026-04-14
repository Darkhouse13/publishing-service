'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

interface NavItem {
  label: string;
  href: string;
}

const navItems: NavItem[] = [
  { label: 'Dashboard', href: '/dashboard' },
  { label: 'Connections', href: '/connections' },
  { label: 'Credentials', href: '/credentials' },
  { label: 'Runs', href: '/runs' },
  { label: 'Articles', href: '/articles' },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed top-0 left-0 w-[300px] h-screen bg-panel border-r-[3px] border-base flex flex-col z-50">
      {/* Logo / Brand */}
      <div className="h-24 flex items-center px-6 border-b-[3px] border-base">
        <h1 className="text-xl font-black uppercase tracking-widest">
          Publishing
        </h1>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4">
        <ul className="space-y-0">
          {navItems.map((item) => {
            const isActive =
              item.href === '/dashboard'
                ? pathname === '/dashboard' || pathname === '/'
                : pathname.startsWith(item.href);

            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`
                    block px-6 py-4 font-black uppercase tracking-widest text-sm
                    transition-colors duration-150
                    ${
                      isActive
                        ? 'bg-accent text-base'
                        : 'text-base hover:bg-accent/10'
                    }
                  `}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t-[3px] border-base">
        <p className="text-xs font-bold uppercase tracking-widest text-muted">
          v0.1.0
        </p>
      </div>
    </aside>
  );
}
