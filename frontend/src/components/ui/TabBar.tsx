'use client';

import { HTMLAttributes, forwardRef } from 'react';

/* ----------------------------------------------------------------
   TabBar — Neo-Brutalist Horizontal Tabs
   - Row of horizontal tabs, all uppercase
   - Active tab gets accent (#ffcc00) background
   - Zero border-radius, 3px borders
   ---------------------------------------------------------------- */

interface Tab {
  /** Unique key for the tab */
  key: string;
  /** Display label (will be rendered uppercase) */
  label: string;
}

interface TabBarProps extends Omit<HTMLAttributes<HTMLDivElement>, 'onChange'> {
  /** Array of tab definitions */
  tabs: Tab[];
  /** Currently active tab key */
  activeTab: string;
  /** Called when a tab is clicked */
  onChange: (tabKey: string) => void;
}

const TabBar = forwardRef<HTMLDivElement, TabBarProps>(
  ({ tabs, activeTab, onChange, className = '', ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`flex border-[3px] border-base rounded-none ${className}`}
        {...props}
      >
        {tabs.map((tab) => {
          const isActive = tab.key === activeTab;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => onChange(tab.key)}
              className={`
                flex-1
                px-4 py-3
                font-black uppercase tracking-widest text-xs
                border-[3px] border-base
                rounded-none
                transition-colors duration-150
                focus:outline-none
                ${isActive
                  ? 'bg-accent text-base'
                  : 'bg-white text-base hover:bg-panel'
                }
              `}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
    );
  }
);

TabBar.displayName = 'TabBar';

export default TabBar;
