'use client';

import { useState } from 'react';
import Shell, { type Tab } from '@/components/Shell';
import Dashboard from '@/components/Dashboard';
import BillsTable from '@/components/BillsTable';
import UsersTable from '@/components/UsersTable';
import BillDetail from '@/components/BillDetail';
import UserDetail from '@/components/UserDetail';
import Scans from '@/components/Scans';
import Broadcasts from '@/components/Broadcasts';
import ScanModes from '@/components/ScanModes';
import Reminders from '@/components/Reminders';
import Feedback from '@/components/Feedback';
import SupportContact from '@/components/SupportContact';
import SenderAccounts from '@/components/SenderAccounts';
import ProPricing from '@/components/ProPricing';
import PromoCodes from '@/components/PromoCodes';
import ProGrants from '@/components/ProGrants';
import Labeling from '@/components/Labeling';
import Places from '@/components/Places';
import Dishes from '@/components/Dishes';
import BotQueue from '@/components/BotQueue';

type View =
  | { screen: 'tab'; tab: Tab }
  | { screen: 'bill'; id: number }
  | { screen: 'user'; id: number };

/**
 * One page with tabs rather than routes: a static export has no server to
 * resolve deep links. Detail screens live in the SPA state and keep a tiny back
 * stack for admin drill-downs.
 */
export default function AdminPage() {
  const [view, setView] = useState<View>({ screen: 'tab', tab: 'dashboard' });
  const [backStack, setBackStack] = useState<View[]>([]);

  const activeTab: Tab =
    view.screen === 'tab' ? view.tab : view.screen === 'bill' ? 'bills' : 'users';

  const openView = (next: View) => {
    setBackStack((stack) => [...stack, view]);
    setView(next);
  };

  const openTab = (tab: Tab) => {
    setBackStack([]);
    setView({ screen: 'tab', tab });
  };

  const goBack = () => {
    const previous = backStack.at(-1);
    setBackStack((stack) => stack.slice(0, -1));
    setView(previous ?? { screen: 'tab', tab: activeTab });
  };

  return (
    <Shell tab={activeTab} onTabChange={openTab}>
      {view.screen === 'tab' && view.tab === 'dashboard' && <Dashboard />}
      {view.screen === 'tab' && view.tab === 'bills' && (
        <BillsTable
          onOpenBill={(id) => openView({ screen: 'bill', id })}
          onOpenUser={(id) => openView({ screen: 'user', id })}
        />
      )}
      {view.screen === 'tab' && view.tab === 'users' && (
        <UsersTable onOpenUser={(id) => openView({ screen: 'user', id })} />
      )}
      {view.screen === 'tab' && view.tab === 'scans' && <Scans />}
      {view.screen === 'tab' && view.tab === 'broadcasts' && <Broadcasts />}
      {view.screen === 'tab' && view.tab === 'scan-modes' && <ScanModes />}
      {view.screen === 'tab' && view.tab === 'catalog' && (
        <div className="space-y-8">
          <Labeling />
          <Places />
          <Dishes />
        </div>
      )}
      {view.screen === 'tab' && view.tab === 'reminders' && (
        <Reminders
          onOpenBill={(id) => openView({ screen: 'bill', id })}
          onOpenUser={(id) => openView({ screen: 'user', id })}
        />
      )}
      {view.screen === 'tab' && view.tab === 'pro' && (
        <div className="space-y-6">
          <ProPricing />
          <PromoCodes />
        </div>
      )}
      {view.screen === 'tab' && view.tab === 'subscriptions' && (
        <ProGrants onOpenUser={(id) => openView({ screen: 'user', id })} />
      )}
      {view.screen === 'tab' && view.tab === 'senders' && <SenderAccounts />}
      {view.screen === 'tab' && view.tab === 'bot-queue' && <BotQueue />}
      {view.screen === 'tab' && view.tab === 'support' && (
        <div className="space-y-6">
          <SupportContact />
          <section>
            <h2 className="mb-1 font-bold">Отзывы</h2>
            <p className="mb-3 text-sm text-muted">Из формы обратной связи, которая была в приложении раньше.</p>
            <Feedback onOpenUser={(id) => openView({ screen: 'user', id })} />
          </section>
        </div>
      )}
      {view.screen === 'bill' && (
        <BillDetail
          id={view.id}
          onClose={goBack}
          onOpenUser={(id) => openView({ screen: 'user', id })}
        />
      )}
      {view.screen === 'user' && (
        <UserDetail
          id={view.id}
          onClose={goBack}
          onOpenBill={(id) => openView({ screen: 'bill', id })}
        />
      )}
    </Shell>
  );
}
