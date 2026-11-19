# Scholar Tracker — Master Requirements

**Project goal:** Build a secure, mobile-friendly school management and attendance system for schools in Kenya.

**Status:** Planning document. Listing a requirement does not mean it is implemented. Features must be built, tested, and reviewed before being marked complete.

## 1. School management

1. School registration and setup.
2. School administrator dashboard.
3. Create and manage classes.
4. Create multiple streams under each class.
5. Register and manage students.
6. Register and manage teachers.
7. Assign subjects to teachers.
8. Assign teachers to classes and streams.
9. Manage school timetables.
10. Keep each school's data separate.
11. School profile, name, logo and contact information.
12. Transfer students between classes or streams.
13. Manage academic years and school terms.
14. Configure school-specific settings.

## 2. Authentication and user profiles

15. Sign in using Google.
16. Sign in using email.
17. Sign in using a phone number.
18. Secure account recovery.
19. Profiles for administrators, teachers, students and parents.
20. Profile photos for supported user roles.
21. Account invitations and registration approval.
22. Role-based access permissions.
23. Login history.
24. Secure profile-photo storage.
25. Account verification.
26. Secure logout and session management.

## 3. Parents' portal

27. Individual parent and guardian accounts.
28. Verify parent email address or phone number.
29. Link a verified parent to their child.
30. Allow a maximum of two verified parent or guardian accounts per student.
31. Allow a parent to view multiple linked children.
32. View a child's attendance.
33. View academic reports.
34. View the school calendar.
35. View published seating arrangements.
36. Receive attendance notifications.
37. Receive school announcements.
38. Receive timetable-change notifications.
39. View permitted student information.
40. Protect other students' private information.

## 4. Attendance tracking

41. Daily attendance registers.
42. Lesson-by-lesson attendance.
43. Subject teachers can mark attendance for assigned lessons.
44. Teachers see only their authorized classes.
45. Search students by name or admission number.
46. Mark students Present.
47. Mark students Absent.
48. Record Excused absences.
49. Record Late arrivals.
50. Review attendance before submitting it.
51. Prevent duplicate attendance records.
52. View attendance history by student.
53. View attendance by class, stream, date and lesson.
54. Allow authorized corrections.
55. Record who changed an attendance entry and when.
56. Notify parents about recorded absences.
57. Provide administrators with attendance reports.
58. Identify repeated absence patterns.
59. Track which classes have submitted attendance.
60. Support reporting by term and academic year.

**Attendance safety rule:** Opening a register is not proof that a student is physically present. Teachers must review and confirm attendance before submission.

## 5. Teacher and lesson management

61. Individual teacher dashboard.
62. Subject teacher assignments.
63. Class teacher assignments.
64. Lesson-specific attendance registers.
65. Teacher timetable.
66. Show only relevant lessons on each teacher's dashboard.
67. Assign substitute teachers.
68. Restrict substitutes to authorized classes and periods.
69. Record lesson attendance submissions.
70. Allow administrators to review teacher activity.
71. Link each lesson to its class, stream and subject.
72. Prevent unauthorized changes to lesson records.

## 6. Classroom seating arrangements

73. Create a classroom seating layout.
74. Configure rows, columns and desks.
75. Add a teacher's desk.
76. Assign students to seats.
77. Prevent two students from occupying the same seat.
78. Allow authorized administrators to create and edit layouts.
79. Publish approved seating arrangements.
80. Allow class teachers to edit only when authorized.
81. Allow subject teachers to view published arrangements.
82. Allow parents to view only their own child's published seating position.
83. Prevent parents from editing seating arrangements.
84. Prevent unauthorized subject teachers from changing arrangements.
85. Record seating changes in an audit history.
86. Update arrangements when students transfer.
87. Support mobile-friendly seating layouts.

## 7. Academic reports

88. Record student marks.
89. Calculate grades using school-configured grading rules.
90. Record subject performance.
91. Generate student progress reports.
92. Generate class performance reports.
93. Generate stream performance reports.
94. Compare academic performance across terms.
95. Analyze attendance and academic performance together.
96. Allow parents to view only their own children's reports.
97. Keep historical reports available to authorized users.
98. Restrict report editing to authorized staff.
99. Record important changes to marks and grades.

## 8. School calendar

100. Create a school calendar.
101. Provide monthly, weekly and daily views.
102. Add school events.
103. Add term dates.
104. Add holidays.
105. Add examination dates.
106. Add meetings and school activities.
107. Include event descriptions and locations.
108. Allow administrators to create, edit, publish and cancel events.
109. Support class-specific events.
110. Show relevant events in the parents' portal.
111. Send event reminders.
112. Support recurring events.
113. Maintain a history of important calendar changes.
114. Make the calendar mobile-friendly.

## 9. In-app notifications

115. Add a notification bell.
116. Show unread notification counts.
117. Send attendance alerts.
118. Send school announcements.
119. Send calendar reminders.
120. Send timetable-change alerts.
121. Notify administrators about important system events.
122. Deliver notifications according to user roles.
123. Maintain notification history.
124. Allow users to mark notifications as read.
125. Allow users to mark all notifications as read.
126. Provide notification preferences.
127. Link notifications to relevant pages.
128. Track delivery status where supported.
129. Avoid duplicate notifications.

## 10. Administrator dashboard

130. Show whole-school statistics.
131. Display all classes and streams.
132. Show student totals by class and stream.
133. Show teacher totals and assignments.
134. Display attendance summaries.
135. Filter attendance by date, class and stream.
136. Manage class directors.
137. Provide quick navigation to school management functions.
138. Display outstanding attendance submissions.
139. Provide access to student and teacher directories.
140. Display useful alerts and administrative tasks.
141. Keep the dashboard separate from the full-school timetable.
142. Show different dashboards according to user roles.

## 11. Class director management

143. Allow an administrator to appoint a class director.
144. Configure one class director per class or stream, according to school policy.
145. Allow an administrator to replace a class director.
146. Display the director's identity in the relevant class profile.
147. Give class directors limited, specific permissions.
148. Prevent class directors from changing official attendance by default.
149. Record director appointment and replacement history.
150. Review or remove assignments when staff or students transfer.
151. Allow administrators to supervise class directors.

## 12. Student profiles and teacher directory

152. Allow class directors to submit student profile requests.
153. Require administrator approval before activating requested student profiles.
154. Allow class directors to request subject teacher assignments.
155. Require administrator approval for teacher assignments.
156. Create a searchable Teachers Directory.
157. Display teacher names and profile photos.
158. Display subjects taught by each teacher.
159. Display assigned classes and streams.
160. Show teacher account status.
161. Allow administrators to register and edit teacher records.
162. Allow administrators to assign subjects, classes and streams.
163. Allow authorized administrators to deactivate accounts.
164. Connect teacher assignments to timetables and attendance registers.
165. Record important teacher-directory changes.

## 13. Teaching staff timetable

166. Give every teacher an individual timetable.
167. Provide weekly and daily timetable views.
168. Display lesson times, subjects, classes and rooms.
169. Allow administrators to create and update timetables.
170. Detect teacher timetable conflicts.
171. Detect classroom or room-booking conflicts.
172. Notify affected teachers when timetables change.
173. Link timetable entries to attendance registers.
174. Integrate timetable entries with the school calendar.

## 14. Cybersecurity and data protection

175. Protect user accounts with secure authentication.
176. Require multi-factor authentication for administrators where supported.
177. Never store passwords as plain text; use a recognised password-hashing method.
178. Limit repeated failed login attempts.
179. Secure password resets and account recovery.
180. Manage login sessions securely.
181. Enforce permissions on the backend, not just in the user interface.
182. Isolate each school's data.
183. Ensure parents can access only their verified children's records.
184. Restrict teachers to authorized classes, subjects and records.
185. Use HTTPS to protect data in transit.
186. Restrict database access and protect stored information.
187. Validate submitted data.
188. Protect against common web vulnerabilities, including SQL injection and cross-site scripting.
189. Keep API keys and other secrets out of public GitHub code.
190. Record important actions in security audit logs.
191. Create protected backups and test recovery.
192. Update application dependencies and security components.
193. Collect only necessary student information and restrict access.
194. Test authentication, permissions and common vulnerabilities before releases.
195. Establish a response process for suspected account compromise or data leaks.

## 15. User interface and accessibility

- Mobile-responsive pages for phones, tablets and computers.
- Simple navigation for administrators, teachers, parents and students.
- Clear attendance status indicators.
- Search and filtering for relevant records.
- Helpful validation and error messages.
- Loading indicators and success confirmations.
- Readable text, accessible forms and keyboard-friendly navigation.
- Performance suitable for ordinary phones and slower internet connections.
- Dashboard widgets that show information relevant to the signed-in user's role.
- Keep the administrator's whole-school overview separate from the detailed timetable.

## 16. Truancy prevention and school improvement

- Identify repeated absences and patterns of lateness.
- Alert authorized staff about concerning attendance trends.
- Notify parents about recorded absences.
- Generate attendance statistics and reports.
- Support communication between teachers and parents.
- Track teacher attendance-submission accountability.
- Help administrators identify students who may need support.
- Explore environmental initiatives, including reducing paper use by replacing physical registers with digital records.

## 17. Delivery phases

1. **Foundation and security:** project structure, configuration, authentication, roles, backend permissions and school data isolation.
2. **School setup:** schools, academic years, classes, streams, students and teacher directory.
3. **Attendance:** assigned lessons, attendance registers, corrections, audit history and reports.
4. **Parents' portal:** verified guardian links, child-specific access, attendance and report viewing.
5. **Calendar and timetable:** school events, teacher schedules, conflict checks and notifications.
6. **Classroom management:** seating plans, class directors and approval workflows.
7. **Reporting and insights:** attendance trends, academic reports and truancy prevention.
8. **Release readiness:** security testing, backups, privacy review, accessibility, monitoring and deployment.

## Definition of done

A feature is not complete merely because its page exists. For each feature, record whether it is **Not Started**, **In Progress**, **Implemented**, or **Tested**. Test the backend permission rules, invalid inputs, normal workflows and failure cases. Do not mark a feature **Tested** until its relevant checks pass.

## Privacy and deployment warning

This document is a plan, not a certification of security or compliance. Do not store real student information in the prototype until authentication, authorization, data protection, backup and recovery controls have been implemented and tested. Follow applicable Kenyan data-protection requirements before school deployment.
