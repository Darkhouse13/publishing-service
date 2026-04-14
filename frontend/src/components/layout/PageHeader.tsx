interface PageHeaderProps {
  title: string;
  children?: React.ReactNode;
}

export default function PageHeader({ title, children }: PageHeaderProps) {
  return (
    <header className="h-24 border-b-[3px] border-base flex items-center justify-between px-8 bg-white">
      <h1 className="text-2xl font-black uppercase tracking-widest">
        {title}
      </h1>
      {children && <div className="flex items-center gap-4">{children}</div>}
    </header>
  );
}
