"use client";

import React, { useEffect, useState, useTransition } from "react";
import { 
  Users, Search, Filter, Phone, Mail, MessageSquare, 
  ShoppingBag, Clock, X, Calendar, DollarSign, ArrowRight, CheckCircle2,
  AlertCircle, ChevronRight, MessageCircle, Info, RefreshCw
} from "lucide-react";

interface CustomerSummary {
  id: string;
  name: string;
  phone: string;
  email: string;
  channel_preference: string;
  total_orders: number;
  total_spent: number;
  tags: string[];
  last_order_date: string | null;
  created_at: string;
}

interface OrderHistory {
  id: string;
  amount: number;
  items: string[];
  status: string;
  created_at: string;
}

interface CommHistory {
  id: string;
  campaign_id: string;
  campaign_name: string;
  channel: string;
  message: string;
  status: string;
  sent_at: string | null;
  delivered_at: string | null;
  opened_at: string | null;
  purchased_at: string | null;
}

interface CustomerActivityResponse {
  customer: CustomerSummary;
  orders: OrderHistory[];
  communications: CommHistory[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function CustomersPage() {
  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Search & Filter state
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedChannel, setSelectedChannel] = useState("");
  const [selectedTag, setSelectedTag] = useState("");
  
  // Selected Customer detail state
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [activityData, setActivityData] = useState<CustomerActivityResponse | null>(null);
  const [loadingActivity, setLoadingActivity] = useState(false);
  const [activeTab, setActiveTab] = useState<"orders" | "comms">("orders");

  // Fetch all customers on load
  const fetchCustomers = async () => {
    try {
      setLoading(true);
      // Fetch up to 200 customers at once for client-side search/filter ease
      let url = `${API_BASE}/customers?limit=200`;
      if (selectedChannel) url += `&channel=${selectedChannel}`;
      if (selectedTag) url += `&tag=${selectedTag}`;

      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to fetch customers");
      const data = await res.json();
      setCustomers(data);
      setError(null);
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to connect to the backend server.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCustomers();
  }, [selectedChannel, selectedTag]);

  // Fetch detailed activity when a customer is selected
  const fetchCustomerActivity = async (id: string) => {
    try {
      setLoadingActivity(true);
      setSelectedCustomerId(id);
      const res = await fetch(`${API_BASE}/customers/${id}/activity`);
      if (!res.ok) throw new Error("Failed to fetch customer activity details");
      const data = await res.json();
      setActivityData(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingActivity(false);
    }
  };

  // Filter customers locally by search term
  const filteredCustomers = customers.filter(c => {
    const term = searchTerm.toLowerCase();
    return (
      c.name.toLowerCase().includes(term) ||
      c.email.toLowerCase().includes(term) ||
      c.phone.toLowerCase().includes(term)
    );
  });

  const getChannelBadge = (channel: string) => {
    switch (channel) {
      case "whatsapp":
        return (
          <span className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 border border-indigo-100">
            <MessageCircle className="h-3 w-3" />
            WhatsApp
          </span>
        );
      case "email":
        return (
          <span className="inline-flex items-center gap-1 rounded-md bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700 border border-blue-100">
            <Mail className="h-3 w-3" />
            Email
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-md bg-zinc-50 px-2 py-0.5 text-xs font-semibold text-zinc-700 border border-zinc-200">
            <Phone className="h-3 w-3" />
            SMS
          </span>
        );
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "purchased":
        return (
          <span className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-0.5 text-3xs font-semibold text-emerald-700 border border-emerald-150">
            Purchased
          </span>
        );
      case "clicked":
        return (
          <span className="inline-flex items-center rounded-md bg-sky-50 px-2 py-0.5 text-3xs font-semibold text-sky-700 border border-sky-150">
            Clicked
          </span>
        );
      case "opened":
        return (
          <span className="inline-flex items-center rounded-md bg-amber-50 px-2 py-0.5 text-3xs font-semibold text-amber-700 border border-amber-150">
            Opened
          </span>
        );
      case "delivered":
        return (
          <span className="inline-flex items-center rounded-md bg-zinc-100 px-2 py-0.5 text-3xs font-semibold text-zinc-700 border border-zinc-200">
            Delivered
          </span>
        );
      case "sent":
        return (
          <span className="inline-flex items-center rounded-md bg-zinc-50 px-2 py-0.5 text-3xs font-semibold text-zinc-650 border border-zinc-200">
            Sent
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center rounded-md bg-rose-50 px-2 py-0.5 text-3xs font-semibold text-rose-700 border border-rose-150">
            Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center rounded-md bg-amber-50 px-2 py-0.5 text-3xs font-semibold text-amber-700 border border-amber-150">
            Queued
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 relative min-h-[calc(100vh-140px)]">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-zinc-200/80 pb-6">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-zinc-900 flex items-center gap-2">
            <Users className="h-5 w-5 text-indigo-650" />
            Customer Directory
          </h1>
          <p className="text-xs text-zinc-500 mt-1">Explore all customer profiles, purchase history, and communication activities</p>
        </div>
        <div className="flex items-center gap-2">
          <button 
            onClick={fetchCustomers} 
            className="inline-flex items-center justify-center p-2 rounded-md border border-zinc-200 bg-white text-zinc-650 hover:bg-zinc-50 transition-colors"
            title="Refresh database records"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Main Content Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Side: Customers list with Search and filters (Takes full width if no selection, else 7 cols) */}
        <div className={`space-y-4 transition-all duration-300 ${selectedCustomerId ? "hidden lg:block lg:col-span-7" : "lg:col-span-12"}`}>
          {/* Controls Bar */}
          <div className="flex flex-col sm:flex-row gap-3 bg-white border border-zinc-200 p-4 rounded-lg shadow-2xs">
            {/* Search Box */}
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-zinc-400" />
              <input
                type="text"
                placeholder="Search by name, email, or phone number..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-9 pr-4 py-2 border border-zinc-200 rounded-md text-xs placeholder-zinc-400 focus:outline-hidden focus:ring-1 focus:ring-indigo-600 focus:border-indigo-600 transition-colors"
              />
            </div>

            {/* Filter Dropdowns */}
            <div className="flex flex-wrap gap-2 shrink-0">
              {/* Channel Filter */}
              <div className="relative flex items-center">
                <Filter className="absolute left-2.5 h-3.5 w-3.5 text-zinc-400 pointer-events-none" />
                <select
                  value={selectedChannel}
                  onChange={(e) => setSelectedChannel(e.target.value)}
                  className="pl-8 pr-6 py-2 border border-zinc-200 rounded-md text-xs bg-white text-zinc-700 focus:outline-hidden focus:ring-1 focus:ring-indigo-600 appearance-none cursor-pointer"
                >
                  <option value="">All Channels</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="sms">SMS</option>
                  <option value="email">Email</option>
                </select>
              </div>

              {/* Tag Filter */}
              <div className="relative flex items-center">
                <select
                  value={selectedTag}
                  onChange={(e) => setSelectedTag(e.target.value)}
                  className="px-3 py-2 border border-zinc-200 rounded-md text-xs bg-white text-zinc-700 focus:outline-hidden focus:ring-1 focus:ring-indigo-600 appearance-none cursor-pointer"
                >
                  <option value="">All Tags</option>
                  <option value="vip">VIP</option>
                  <option value="new">New</option>
                  <option value="at-risk">At-Risk</option>
                </select>
              </div>
            </div>
          </div>

          {/* Table Directory */}
          {loading ? (
            <div className="rounded-lg border border-zinc-200 bg-white p-20 flex flex-col justify-center items-center text-xs text-zinc-400">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900 mb-3" />
              Loading customer profiles...
            </div>
          ) : error ? (
            <div className="rounded-lg border border-red-200 bg-red-50/50 p-6 text-center">
              <p className="text-xs text-red-700">{error}</p>
            </div>
          ) : filteredCustomers.length === 0 ? (
            <div className="rounded-lg border border-dashed border-zinc-200 bg-white p-12 text-center text-zinc-400 text-xs">
              <Info className="h-8 w-8 mx-auto text-zinc-300 mb-2" />
              <p className="font-semibold text-zinc-700">No customers found</p>
              <p className="mt-1 text-3xs text-zinc-450">Try adjusting your filters or search keyword.</p>
            </div>
          ) : (
            <div className="rounded-lg border border-zinc-200 bg-white overflow-hidden shadow-2xs">
              <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
                <table className="min-w-full divide-y divide-zinc-200 text-left text-xs">
                  <thead className="bg-zinc-50 text-zinc-500 font-semibold uppercase tracking-wider text-3xs border-b border-zinc-200 sticky top-0 z-10">
                    <tr>
                      <th scope="col" className="px-4 py-3">Customer</th>
                      <th scope="col" className="px-4 py-3">Pref. Channel</th>
                      <th scope="col" className="px-4 py-3">Stats</th>
                      <th scope="col" className="px-4 py-3 hidden sm:table-cell">Tags</th>
                      <th scope="col" className="px-4 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100 bg-white">
                    {filteredCustomers.map((cust) => (
                      <tr 
                        key={cust.id} 
                        onClick={() => fetchCustomerActivity(cust.id)}
                        className={`hover:bg-zinc-50/70 transition-colors cursor-pointer ${
                          selectedCustomerId === cust.id ? "bg-indigo-50/40 hover:bg-indigo-50/40" : ""
                        }`}
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2.5">
                            <div className="h-8 w-8 rounded-full bg-indigo-50 border border-indigo-150 flex items-center justify-center font-bold text-xs text-indigo-700 shrink-0">
                              {cust.name.split(" ").map(n => n[0]).slice(0, 2).join("")}
                            </div>
                            <div className="min-w-0">
                              <p className="font-semibold text-zinc-900 truncate">{cust.name}</p>
                              <p className="text-3xs text-zinc-400 truncate flex items-center gap-1.5 mt-0.5">
                                <span className="flex items-center gap-0.5"><Mail className="h-2.5 w-2.5" />{cust.email}</span>
                                <span className="text-zinc-300">•</span>
                                <span className="flex items-center gap-0.5"><Phone className="h-2.5 w-2.5" />{cust.phone}</span>
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          {getChannelBadge(cust.channel_preference)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <p className="font-semibold text-zinc-850">₹{cust.total_spent.toLocaleString()}</p>
                          <p className="text-3xs text-zinc-450 mt-0.5">{cust.total_orders} order{cust.total_orders !== 1 ? "s" : ""}</p>
                        </td>
                        <td className="px-4 py-3 hidden sm:table-cell">
                          <div className="flex flex-wrap gap-1 max-w-[150px]">
                            {cust.tags && cust.tags.length > 0 ? (
                              cust.tags.map((t) => (
                                <span 
                                  key={t} 
                                  className={`inline-flex items-center px-1 py-0.2 rounded-sm text-4xs font-bold uppercase tracking-wider border ${
                                    t === "vip" 
                                      ? "bg-amber-50 text-amber-700 border-amber-200" 
                                      : t === "new" 
                                        ? "bg-emerald-50 text-emerald-700 border-emerald-250" 
                                        : "bg-rose-50 text-rose-700 border-rose-200"
                                  }`}
                                >
                                  {t}
                                </span>
                              ))
                            ) : (
                              <span className="text-zinc-350 italic text-3xs">-</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right whitespace-nowrap">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              fetchCustomerActivity(cust.id);
                            }}
                            className="inline-flex p-1.5 rounded-md hover:bg-zinc-100 text-zinc-500 hover:text-zinc-900 transition-colors"
                          >
                            <ChevronRight className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Right Side: Detailed activity slide-in/panel (Takes 5 cols) */}
        {selectedCustomerId && (
          <div className="col-span-1 lg:col-span-5 bg-white border border-zinc-200 rounded-lg shadow-sm overflow-hidden sticky top-20">
            {/* Details Panel Header */}
            <div className="border-b border-zinc-200 p-4 bg-zinc-50 flex items-center justify-between">
              <h2 className="text-sm font-bold text-zinc-950 flex items-center gap-1.5">
                <Info className="h-4 w-4 text-indigo-650" />
                Marketer's Customer Room
              </h2>
              <button 
                onClick={() => { setSelectedCustomerId(null); setActivityData(null); }}
                className="p-1 rounded-md text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {loadingActivity ? (
              <div className="h-80 flex flex-col justify-center items-center text-xs text-zinc-400">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900 mb-3" />
                Loading activity logs...
              </div>
            ) : activityData ? (
              <div className="divide-y divide-zinc-200">
                {/* 1. Core Profile Details */}
                <div className="p-4 space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-full bg-indigo-100 border border-indigo-200 flex items-center justify-center font-bold text-sm text-indigo-800 shrink-0">
                      {activityData.customer.name.split(" ").map(n => n[0]).slice(0, 2).join("")}
                    </div>
                    <div>
                      <h3 className="font-bold text-sm text-zinc-950">{activityData.customer.name}</h3>
                      <p className="text-3xs text-zinc-450 mt-0.5">ID: {activityData.customer.id}</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs py-2 bg-zinc-50/60 p-2.5 rounded border border-zinc-150">
                    <div className="space-y-1">
                      <span className="text-4xs font-bold text-zinc-400 uppercase tracking-wider block">Email Address</span>
                      <span className="font-medium text-zinc-800 break-all">{activityData.customer.email}</span>
                    </div>
                    <div className="space-y-1">
                      <span className="text-4xs font-bold text-zinc-400 uppercase tracking-wider block">Phone Number</span>
                      <span className="font-medium text-zinc-800">{activityData.customer.phone}</span>
                    </div>
                    <div className="space-y-1 mt-1">
                      <span className="text-4xs font-bold text-zinc-400 uppercase tracking-wider block">Channel Channel</span>
                      <span className="font-semibold text-zinc-850 flex items-center gap-1">
                        {activityData.customer.channel_preference === "whatsapp" && <MessageCircle className="h-3.5 w-3.5 text-emerald-600" />}
                        {activityData.customer.channel_preference === "email" && <Mail className="h-3.5 w-3.5 text-blue-600" />}
                        {activityData.customer.channel_preference === "sms" && <Phone className="h-3.5 w-3.5 text-zinc-650" />}
                        {activityData.customer.channel_preference}
                      </span>
                    </div>
                    <div className="space-y-1 mt-1">
                      <span className="text-4xs font-bold text-zinc-400 uppercase tracking-wider block">Tags</span>
                      <div className="flex gap-1 flex-wrap">
                        {activityData.customer.tags.map(t => (
                          <span key={t} className="px-1 py-0.2 rounded-sm bg-zinc-100 text-zinc-700 border border-zinc-200 text-4xs font-bold uppercase">{t}</span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Core Value KPIs */}
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="border border-zinc-200 bg-white rounded p-2">
                      <span className="text-4xs font-bold text-zinc-400 uppercase tracking-wider block">Total Spent</span>
                      <span className="text-sm font-extrabold text-zinc-900">₹{activityData.customer.total_spent.toLocaleString()}</span>
                    </div>
                    <div className="border border-zinc-200 bg-white rounded p-2">
                      <span className="text-4xs font-bold text-zinc-400 uppercase tracking-wider block">Total Orders</span>
                      <span className="text-sm font-extrabold text-zinc-900">{activityData.customer.total_orders}</span>
                    </div>
                    <div className="border border-zinc-200 bg-white rounded p-2">
                      <span className="text-4xs font-bold text-zinc-400 uppercase tracking-wider block">Avg Ticket</span>
                      <span className="text-sm font-extrabold text-zinc-900">
                        ₹{activityData.customer.total_orders > 0 
                          ? Math.round(activityData.customer.total_spent / activityData.customer.total_orders).toLocaleString()
                          : "0"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* 2. Tabs Selector */}
                <div>
                  <div className="flex border-b border-zinc-200 bg-zinc-50/50">
                    <button
                      onClick={() => setActiveTab("orders")}
                      className={`flex-1 py-2 text-xs font-bold border-b-2 transition-all flex items-center justify-center gap-1.5 ${
                        activeTab === "orders" 
                          ? "border-indigo-600 text-indigo-650 bg-white" 
                          : "border-transparent text-zinc-500 hover:text-zinc-900 hover:bg-zinc-50/30"
                      }`}
                    >
                      <ShoppingBag className="h-3.5 w-3.5" />
                      Orders ({activityData.orders.length})
                    </button>
                    <button
                      onClick={() => setActiveTab("comms")}
                      className={`flex-1 py-2 text-xs font-bold border-b-2 transition-all flex items-center justify-center gap-1.5 ${
                        activeTab === "comms" 
                          ? "border-indigo-600 text-indigo-650 bg-white" 
                          : "border-transparent text-zinc-500 hover:text-zinc-900 hover:bg-zinc-50/30"
                      }`}
                    >
                      <MessageSquare className="h-3.5 w-3.5" />
                      Campaign Runs ({activityData.communications.length})
                    </button>
                  </div>

                  {/* Tab Content */}
                  <div className="p-4 max-h-[360px] overflow-y-auto bg-white/30">
                    {activeTab === "orders" ? (
                      /* Orders Tab */
                      activityData.orders.length === 0 ? (
                        <div className="text-center text-zinc-400 py-10 text-xs">
                          No purchases recorded in CRM database.
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {activityData.orders.map((o) => (
                            <div key={o.id} className="border border-zinc-200 rounded-md bg-white p-3 hover:border-zinc-300 transition-colors">
                              <div className="flex items-center justify-between text-xs">
                                <span className="font-semibold text-zinc-800">Order ID: ...{o.id.slice(-8)}</span>
                                <span className="font-extrabold text-zinc-950">₹{o.amount.toLocaleString()}</span>
                              </div>
                              <div className="flex items-center gap-1.5 text-3xs text-zinc-400 mt-1">
                                <Calendar className="h-3 w-3" />
                                {new Date(o.created_at).toLocaleString()}
                              </div>
                              <div className="flex flex-wrap gap-1 mt-2.5">
                                {o.items.map((it, idx) => (
                                  <span key={idx} className="bg-zinc-50 border border-zinc-150 text-zinc-650 px-1.5 py-0.5 rounded text-4xs font-medium">
                                    {it}
                                  </span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      )
                    ) : (
                      /* Communications Tab */
                      activityData.communications.length === 0 ? (
                        <div className="text-center text-zinc-400 py-10 text-xs">
                          No marketing communications sent to this customer.
                        </div>
                      ) : (
                        <div className="space-y-4">
                          {activityData.communications.map((c) => (
                            <div key={c.id} className="border border-zinc-200 rounded-md bg-white p-3 hover:border-zinc-300 transition-colors relative">
                              <div className="flex items-center justify-between text-xs mb-1.5">
                                <span className="font-bold text-zinc-900 truncate max-w-[180px]">{c.campaign_name}</span>
                                {getStatusBadge(c.status)}
                              </div>
                              
                              <p className="text-3xs text-zinc-600 bg-zinc-50/70 p-2 rounded border border-zinc-100 font-serif leading-normal whitespace-pre-wrap">
                                {c.message}
                              </p>

                              <div className="grid grid-cols-2 gap-y-1.5 gap-x-2 text-4xs text-zinc-400 mt-2.5 pt-2 border-t border-zinc-100">
                                <div>
                                  <span className="font-bold uppercase tracking-wider block text-[8px] text-zinc-400">Channel</span>
                                  <span className="font-semibold text-zinc-650 uppercase">{c.channel}</span>
                                </div>
                                {c.sent_at && (
                                  <div>
                                    <span className="font-bold uppercase tracking-wider block text-[8px] text-zinc-400">Sent At</span>
                                    <span>{new Date(c.sent_at).toLocaleTimeString()}</span>
                                  </div>
                                )}
                                {c.delivered_at && (
                                  <div>
                                    <span className="font-bold uppercase tracking-wider block text-[8px] text-zinc-400">Delivered At</span>
                                    <span>{new Date(c.delivered_at).toLocaleTimeString()}</span>
                                  </div>
                                )}
                                {c.opened_at && (
                                  <div>
                                    <span className="font-bold uppercase tracking-wider block text-[8px] text-zinc-400">Opened At</span>
                                    <span>{new Date(c.opened_at).toLocaleTimeString()}</span>
                                  </div>
                                )}
                                {c.purchased_at && (
                                  <div className="col-span-2">
                                    <span className="font-bold uppercase tracking-wider block text-[8px] text-emerald-600">Purchased On Callback</span>
                                    <span className="text-emerald-700 font-semibold">{new Date(c.purchased_at).toLocaleString()}</span>
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )
                    )}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
