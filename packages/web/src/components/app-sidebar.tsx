import { Link, useLocation } from "react-router-dom";
import {
  ScrollText,
  Settings,
  Bell,
  LayoutDashboard,
  Server,
  ListTodo,
  Inbox,
  Send,
  Play,
  History,
  GitBranch,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { ConnectionStatus } from "./connection-status";
import { ThemeToggle } from "./theme-toggle";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";

const navSections = [
  {
    items: [{ href: "/", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Tasks",
    items: [
      { href: "/tasks", label: "Tasks", icon: ListTodo },
      { href: "/active", label: "Active", icon: Play },
      { href: "/history", label: "Results", icon: History },
      { href: "/events", label: "Event Log", icon: ScrollText },
      { href: "/send", label: "Manual Send", icon: Send },
    ],
  },
  {
    label: "Scheduling",
    items: [
      { href: "/workflows", label: "Workflows", icon: GitBranch },
      { href: "/alerts", label: "Alerts", icon: Bell },
    ],
  },
  {
    label: "Infrastructure",
    items: [
      { href: "/workers", label: "Workers", icon: Server },
      { href: "/queues", label: "Queues", icon: Inbox },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export function AppSidebar() {
  const { pathname } = useLocation();
  const { toggleSidebar, state } = useSidebar();

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link to="/">
                <img
                  src="/logo.svg"
                  alt="CeleryHub"
                  className="h-6 w-6 shrink-0 dark:invert"
                />
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">CeleryHub</span>
                  <span className="truncate text-xs text-muted-foreground">
                    Celery Monitor
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {navSections.map((section, si) => (
          <SidebarGroup key={si}>
            {section.label && (
              <SidebarGroupLabel>{section.label}</SidebarGroupLabel>
            )}
            <SidebarGroupContent>
              <SidebarMenu>
                {section.items.map(({ href, label, icon: Icon }) => {
                  const active =
                    href === "/" ? pathname === "/" : pathname.startsWith(href);

                  return (
                    <SidebarMenuItem key={href}>
                      <SidebarMenuButton
                        asChild
                        isActive={active}
                        tooltip={label}
                      >
                        <Link to={href}>
                          <Icon />
                          <span>{label}</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton tooltip="Connection">
              <ConnectionStatus />
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <ThemeToggle />
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
      <button
        onClick={toggleSidebar}
        className="absolute top-4 -right-3 z-30 hidden h-6 w-6 items-center justify-center rounded-full border bg-background text-muted-foreground shadow-sm hover:text-foreground transition-colors md:flex"
      >
        {state === "expanded" ? (
          <ChevronsLeft className="h-3.5 w-3.5" />
        ) : (
          <ChevronsRight className="h-3.5 w-3.5" />
        )}
      </button>
    </Sidebar>
  );
}
