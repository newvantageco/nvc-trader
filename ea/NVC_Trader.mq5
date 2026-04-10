//+------------------------------------------------------------------+
//|  NVC Trader — Expert Advisor for MetaTrader 5                   |
//|  New Vantage Co                                                  |
//|                                                                  |
//|  Receives JSON signal packets from the Python Claude agent       |
//|  via ZeroMQ PULL socket and executes trades on MT5.             |
//|  Reports fills back to Python via ZeroMQ PUSH socket.           |
//+------------------------------------------------------------------+

#property copyright "New Vantage Co"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

// ─── ZeroMQ DLL ─────────────────────────────────────────────────────────────
// Requires: Darwinex ZMQ library for MQL5
// https://github.com/darwinex/dwx-zeromq-connector
#include <Zmq/Zmq.mqh>

// ─── Inputs ──────────────────────────────────────────────────────────────────
input string   InpHost       = "localhost";  // Python engine host
input int      InpSignalPort = 5555;         // Receive signals on this port
input int      InpFillPort   = 5556;         // Send fills to Python on this port
input bool     InpLiveTrading = false;       // Set true for live (NOT demo) trading
input double   InpMaxLot     = 5.0;         // Hard cap on lot size
input int      InpMagicNum   = 20260101;     // Magic number for NVC orders

// ─── Globals ─────────────────────────────────────────────────────────────────
CTrade         g_trade;
CPositionInfo  g_position;
Context*       g_ctx;
Socket*        g_pull;
Socket*        g_push;
bool           g_connected = false;

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   g_trade.SetMagicNumber(InpMagicNum);
   g_trade.SetDeviationInPoints(30);
   g_trade.SetTypeFilling(ORDER_FILLING_FOK);

   if(!ConnectZMQ())
   {
      Print("[NVC] ERROR: ZeroMQ connection failed");
      return INIT_FAILED;
   }

   Print("[NVC] NVC Trader v1.0 initialized. Listening on port ", InpSignalPort);
   EventSetMillisecondTimer(100);  // Poll ZMQ every 100ms
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   DisconnectZMQ();
   Print("[NVC] EA deinitialized. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Timer — poll ZeroMQ for incoming signals                         |
//+------------------------------------------------------------------+
void OnTimer()
{
   if(!g_connected) return;

   ZmqMsg msg;
   if(g_pull.recv(msg, true))  // non-blocking
   {
      string raw = msg.getData();
      Print("[NVC] Signal received: ", StringSubstr(raw, 0, 200));
      ProcessSignal(raw);
   }
}

//+------------------------------------------------------------------+
//| Process incoming JSON signal from Claude agent                   |
//+------------------------------------------------------------------+
void ProcessSignal(string raw)
{
   // Parse action type first
   string action = ExtractJsonString(raw, "action");

   if(action == "CLOSE")
   {
      long ticket = (long)ExtractJsonDouble(raw, "ticket");
      ClosePosition(ticket, ExtractJsonString(raw, "reason"));
      return;
   }

   if(action == "MODIFY")
   {
      long ticket = (long)ExtractJsonDouble(raw, "ticket");
      double new_sl = ExtractJsonDouble(raw, "new_sl");
      double new_tp = ExtractJsonDouble(raw, "new_tp");
      ModifyPosition(ticket, new_sl, new_tp);
      return;
   }

   // Default: trade execution signal
   string signal_id  = ExtractJsonString(raw, "signal_id");
   string instrument = ExtractJsonString(raw, "instrument");
   string direction  = ExtractJsonString(raw, "direction");
   double lot_size   = ExtractJsonDouble(raw, "lot_size");
   double stop_loss  = ExtractJsonDouble(raw, "stop_loss");
   double take_profit= ExtractJsonDouble(raw, "take_profit");
   double score      = ExtractJsonDouble(raw, "score");
   string reason     = ExtractJsonString(raw, "reason");

   // Safety guards
   if(lot_size <= 0 || lot_size > InpMaxLot)
   {
      SendFill(signal_id, 0, "REJECTED", 0.0, "Invalid lot size: " + DoubleToString(lot_size));
      return;
   }
   if(score < 0.60)
   {
      SendFill(signal_id, 0, "REJECTED", 0.0, "Score below threshold: " + DoubleToString(score));
      return;
   }

   // Execute
   ExecuteTrade(signal_id, instrument, direction, lot_size, stop_loss, take_profit, reason);
}

//+------------------------------------------------------------------+
//| Execute a trade                                                  |
//+------------------------------------------------------------------+
void ExecuteTrade(string signal_id, string symbol, string direction,
                  double lots, double sl, double tp, string comment)
{
   // Check symbol exists
   if(!SymbolSelect(symbol, true))
   {
      Print("[NVC] ERROR: Symbol not found: ", symbol);
      SendFill(signal_id, 0, "REJECTED", 0.0, "Symbol not found: " + symbol);
      return;
   }

   double price  = (direction == "BUY") ? SymbolInfoDouble(symbol, SYMBOL_ASK)
                                        : SymbolInfoDouble(symbol, SYMBOL_BID);
   ENUM_ORDER_TYPE type = (direction == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;

   Print("[NVC] Executing ", direction, " ", lots, " lots ", symbol,
         " @ ", price, " SL=", sl, " TP=", tp);

   bool result = g_trade.PositionOpen(symbol, type, lots, price, sl, tp,
                                       "NVC|" + signal_id + "|" + comment);

   if(result)
   {
      ulong ticket = g_trade.ResultOrder();
      double fill_price = g_trade.ResultPrice();
      Print("[NVC] FILLED ticket=", ticket, " price=", fill_price);
      SendFill(signal_id, (long)ticket, "FILLED", fill_price, "");
   }
   else
   {
      int error = g_trade.ResultRetcode();
      string err_msg = "MT5 error " + IntegerToString(error);
      Print("[NVC] ORDER FAILED: ", err_msg);
      SendFill(signal_id, 0, "FAILED", 0.0, err_msg);
   }
}

//+------------------------------------------------------------------+
//| Close a position by ticket                                       |
//+------------------------------------------------------------------+
void ClosePosition(long ticket, string reason)
{
   if(g_position.SelectByTicket((ulong)ticket))
   {
      g_trade.PositionClose((ulong)ticket);
      Print("[NVC] Position closed: ticket=", ticket, " reason=", reason);
   }
}

//+------------------------------------------------------------------+
//| Modify a position's SL/TP                                        |
//+------------------------------------------------------------------+
void ModifyPosition(long ticket, double new_sl, double new_tp)
{
   if(g_position.SelectByTicket((ulong)ticket))
   {
      double sl = (new_sl > 0) ? new_sl : g_position.StopLoss();
      double tp = (new_tp > 0) ? new_tp : g_position.TakeProfit();
      g_trade.PositionModify((ulong)ticket, sl, tp);
      Print("[NVC] Position modified: ticket=", ticket, " SL=", sl, " TP=", tp);
   }
}

//+------------------------------------------------------------------+
//| Send fill report back to Python via ZMQ PUSH                     |
//+------------------------------------------------------------------+
void SendFill(string signal_id, long ticket, string status,
              double fill_price, string error_msg)
{
   string json = "{\"signal_id\":\"" + signal_id + "\","
               + "\"ticket\":" + IntegerToString(ticket) + ","
               + "\"status\":\"" + status + "\","
               + "\"fill_price\":" + DoubleToString(fill_price, 5) + ","
               + "\"error\":\"" + error_msg + "\","
               + "\"fill_time\":\"" + TimeToString(TimeCurrent()) + "\"}";

   ZmqMsg reply(json);
   g_push.send(reply);
}

//+------------------------------------------------------------------+
//| ZeroMQ Setup                                                     |
//+------------------------------------------------------------------+
bool ConnectZMQ()
{
   g_ctx  = new Context();
   g_pull = new Socket(g_ctx, ZMQ_PULL);
   g_push = new Socket(g_ctx, ZMQ_PUSH);

   string pull_addr = "tcp://" + InpHost + ":" + IntegerToString(InpSignalPort);
   string push_addr = "tcp://" + InpHost + ":" + IntegerToString(InpFillPort);

   if(!g_pull.connect(pull_addr))
   {
      Print("[NVC] PULL connect failed: ", pull_addr);
      return false;
   }
   if(!g_push.connect(push_addr))
   {
      Print("[NVC] PUSH connect failed: ", push_addr);
      return false;
   }

   g_connected = true;
   Print("[NVC] ZMQ connected. PULL=", pull_addr, " PUSH=", push_addr);
   return true;
}

void DisconnectZMQ()
{
   if(g_pull) { delete g_pull; g_pull = NULL; }
   if(g_push) { delete g_push; g_push = NULL; }
   if(g_ctx)  { delete g_ctx;  g_ctx  = NULL; }
   g_connected = false;
}

//+------------------------------------------------------------------+
//| Minimal JSON helpers (no external JSON lib required)             |
//+------------------------------------------------------------------+
string ExtractJsonString(string json, string key)
{
   string search = "\"" + key + "\":\"";
   int start = StringFind(json, search);
   if(start < 0) return "";
   start += StringLen(search);
   int end = StringFind(json, "\"", start);
   if(end < 0) return "";
   return StringSubstr(json, start, end - start);
}

double ExtractJsonDouble(string json, string key)
{
   string search = "\"" + key + "\":";
   int start = StringFind(json, search);
   if(start < 0) return 0.0;
   start += StringLen(search);
   // Read until comma, } or ]
   string val = "";
   for(int i = start; i < StringLen(json); i++)
   {
      string ch = StringSubstr(json, i, 1);
      if(ch == "," || ch == "}" || ch == "]") break;
      val += ch;
   }
   return StringToDouble(val);
}
//+------------------------------------------------------------------+
