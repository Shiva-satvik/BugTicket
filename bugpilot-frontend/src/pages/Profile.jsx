import { ShieldCheck } from "lucide-react";

import { PageHeader } from "../components/Common.jsx";

import { fmt, getUserName, initials, safeArray } from "../utils";

export default function ProfilePage({ user }) {
  const roles = safeArray(user?.roles);

  const profileDetails = [
    ["Username", user?.username],
    ["Email", user?.email],
    ["Employee ID", user?.employee_id],
    ["Department ID", user?.department_id],
    ["Designation", user?.designation],
    [
      "Roles",
      roles.length > 0 ? roles.join(", ") : "Loaded from access policy",
    ],
  ];

  return (
    <>
      <PageHeader
        eyebrow="ACCOUNT"
        title="Your profile"
        description="Identity and access information returned by your BugPilot backend."
      />

      <section className="panel profile-panel">
        {/* Profile header */}
        <div className="profile-heading">
          <div className="avatar avatar-large">
            {initials(getUserName(user))}
          </div>

          <div>
            <h2>{getUserName(user)}</h2>

            <p>{user?.designation || "BugPilot member"}</p>
          </div>

          <span className="profile-active">
            <span />
            Authenticated
          </span>
        </div>

        {/* Profile information */}
        <div className="profile-details">
          {profileDetails.map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <b>{fmt(value)}</b>
            </div>
          ))}
        </div>

        {/* Access information */}
        <div className="profile-note">
          <ShieldCheck size={17} />

          <span>
            Role-based permissions are enforced by the backend. This page does
            not grant additional access.
          </span>
        </div>
      </section>
    </>
  );
}
