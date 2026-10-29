# Source map: API, database entities và pages

> Mục đích và phạm vi: Tra cứu khai báo tại revision đã kiểm tra; appendix hỗ trợ module guides.
> Đối chiếu mã nguồn tại `aca8e0418a56e44d7e06f370ba5f3ebe5bf41778`. Đây là kiểm tra tĩnh; không xác nhận trạng thái deployment đang chạy.

Mục lục này được trích tĩnh từ Python AST, SQLAlchemy declarations và Next page tree; không khởi động app/OpenAPI. Prefix API mặc định `/api/v1` được ghép với APIRouter prefix. Không liệt kê auto HEAD/OPTIONS, docs/OpenAPI endpoints hoặc coi annotation type là runtime permission. Khi sửa route, kiểm lại composition trong [router.py](../../backend/app/api/v1/router.py).

## Backend route map

| Method | API path | Declaration |
| --- | --- | --- |
| GET | `/api/v1/admin/directory/people` | [admin.py::directory_people](../../backend/app/api/v1/admin.py) |
| GET | `/api/v1/admin/directory/people/{person_id}` | [admin.py::directory_person](../../backend/app/api/v1/admin.py) |
| GET | `/api/v1/admin/directory/classrooms` | [admin.py::directory_classrooms](../../backend/app/api/v1/admin.py) |
| GET | `/api/v1/admin/stats` | [admin.py::stats](../../backend/app/api/v1/admin.py) |
| GET | `/api/v1/admin/users` | [admin.py::users](../../backend/app/api/v1/admin.py) |
| GET | `/api/v1/admin/users/{user_id}` | [admin.py::user_detail](../../backend/app/api/v1/admin.py) |
| PATCH | `/api/v1/admin/users/{user_id}` | [admin.py::update_user](../../backend/app/api/v1/admin.py) |
| DELETE | `/api/v1/admin/users/{user_id}` | [admin.py::delete_user](../../backend/app/api/v1/admin.py) |
| GET | `/api/v1/analytics` | [analytics.py::analytics_dashboard](../../backend/app/api/v1/analytics.py) |
| GET | `/api/v1/analytics/compare` | [analytics.py::compare_attempts](../../backend/app/api/v1/analytics.py) |
| POST | `/api/v1/assets/images` | [assets.py::upload_image](../../backend/app/api/v1/assets.py) |
| POST | `/api/v1/assets/question-images` | [assets.py::upload_question_image](../../backend/app/api/v1/assets.py) |
| POST | `/api/v1/assets/audio` | [assets.py::upload_audio](../../backend/app/api/v1/assets.py) |
| GET | `/api/v1/assets/{asset_id}/content` | [assets.py::get_asset_content](../../backend/app/api/v1/assets.py) |
| PATCH | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}` | [assignment_scheduling.py::update](../../backend/app/api/v1/assignment_scheduling.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignment-progress` | [assignment_scheduling.py::progress](../../backend/app/api/v1/assignment_scheduling.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/progress` | [assignment_scheduling.py::assignment_progress](../../backend/app/api/v1/assignment_scheduling.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/monitoring` | [assignment_scheduling.py::monitoring](../../backend/app/api/v1/assignment_scheduling.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/extensions` | [assignment_scheduling.py::extensions](../../backend/app/api/v1/assignment_scheduling.py) |
| PUT | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/extensions/{student_id}` | [assignment_scheduling.py::extension](../../backend/app/api/v1/assignment_scheduling.py) |
| DELETE | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/extensions/{student_id}` | [assignment_scheduling.py::revoke](../../backend/app/api/v1/assignment_scheduling.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/schedule-history` | [assignment_scheduling.py::history](../../backend/app/api/v1/assignment_scheduling.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignment-calendar` | [assignment_scheduling.py::calendar](../../backend/app/api/v1/assignment_scheduling.py) |
| POST | `/api/v1/attempts` | [attempts.py::start_attempt](../../backend/app/api/v1/attempts.py) |
| GET | `/api/v1/attempts/{attempt_id}` | [attempts.py::get_attempt](../../backend/app/api/v1/attempts.py) |
| DELETE | `/api/v1/attempts/{attempt_id}` | [attempts.py::delete_attempt](../../backend/app/api/v1/attempts.py) |
| POST | `/api/v1/attempts/{attempt_id}/activity` | [attempts.py::record_activity](../../backend/app/api/v1/attempts.py) |
| POST | `/api/v1/attempts/{attempt_id}/navigation` | [attempts.py::record_navigation](../../backend/app/api/v1/attempts.py) |
| POST | `/api/v1/attempts/{attempt_id}/pause` | [attempts.py::pause_attempt](../../backend/app/api/v1/attempts.py) |
| POST | `/api/v1/attempts/{attempt_id}/resume` | [attempts.py::resume_attempt](../../backend/app/api/v1/attempts.py) |
| PUT | `/api/v1/attempts/{attempt_id}/answers/{question_id}` | [attempts.py::save_answer](../../backend/app/api/v1/attempts.py) |
| PUT | `/api/v1/attempts/{attempt_id}/writing/{writing_task_id}` | [attempts.py::save_writing_response](../../backend/app/api/v1/attempts.py) |
| POST | `/api/v1/attempts/{attempt_id}/submit` | [attempts.py::submit_attempt](../../backend/app/api/v1/attempts.py) |
| GET | `/api/v1/attempts/{attempt_id}/review` | [attempts.py::review_attempt](../../backend/app/api/v1/attempts.py) |
| GET | `/api/v1/attempts/{attempt_id}/exam` | [attempts.py::get_exam](../../backend/app/api/v1/attempts.py) |
| GET | `/api/v1/attempts/{attempt_id}/reading-review` | [attempts.py::get_reading_review](../../backend/app/api/v1/attempts.py) |
| GET | `/api/v1/attempts/{attempt_id}/listening-review` | [attempts.py::get_listening_review](../../backend/app/api/v1/attempts.py) |
| GET | `/api/v1/attempts/{attempt_id}/writing-review` | [attempts.py::get_writing_review](../../backend/app/api/v1/attempts.py) |
| PUT | `/api/v1/attempts/{attempt_id}/writing-scores/{writing_task_id}` | [attempts.py::save_writing_task_score](../../backend/app/api/v1/attempts.py) |
| PUT | `/api/v1/attempts/{attempt_id}/flags/{question_id}` | [attempts.py::save_flag](../../backend/app/api/v1/attempts.py) |
| POST | `/api/v1/attempts/{attempt_id}/highlights` | [attempts.py::create_highlight](../../backend/app/api/v1/attempts.py) |
| DELETE | `/api/v1/attempts/{attempt_id}/highlights/{highlight_id}` | [attempts.py::delete_highlight](../../backend/app/api/v1/attempts.py) |
| DELETE | `/api/v1/attempts/{attempt_id}/highlights` | [attempts.py::delete_all_highlights](../../backend/app/api/v1/attempts.py) |
| POST | `/api/v1/auth/register` | [auth.py::register](../../backend/app/api/v1/auth.py) |
| POST | `/api/v1/auth/login` | [auth.py::login](../../backend/app/api/v1/auth.py) |
| POST | `/api/v1/auth/refresh` | [auth.py::refresh](../../backend/app/api/v1/auth.py) |
| POST | `/api/v1/auth/logout` | [auth.py::logout](../../backend/app/api/v1/auth.py) |
| GET | `/api/v1/auth/me` | [auth.py::me](../../backend/app/api/v1/auth.py) |
| GET | `/api/v1/auth/profile` | [auth.py::get_profile](../../backend/app/api/v1/auth.py) |
| PATCH | `/api/v1/auth/profile` | [auth.py::update_profile](../../backend/app/api/v1/auth.py) |
| POST | `/api/v1/auth/change-password` | [auth.py::change_password](../../backend/app/api/v1/auth.py) |
| GET | `/api/v1/auth/oauth/google/start` | [auth.py::google_start](../../backend/app/api/v1/auth.py) |
| GET | `/api/v1/auth/oauth/google/callback` | [auth.py::google_callback](../../backend/app/api/v1/auth.py) |
| DELETE | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}` | [classroom_assignments.py::delete_assignment](../../backend/app/api/v1/classroom_assignments.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignments` | [classroom_assignments.py::assignments](../../backend/app/api/v1/classroom_assignments.py) |
| GET | `/api/v1/me/classrooms/{classroom_id}/assignments` | [classroom_assignments.py::assignments](../../backend/app/api/v1/classroom_assignments.py) |
| POST | `/api/v1/classrooms/{classroom_id}/assignments` | [classroom_assignments.py::create](../../backend/app/api/v1/classroom_assignments.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}` | [classroom_assignments.py::detail](../../backend/app/api/v1/classroom_assignments.py) |
| POST | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/archive` | [classroom_assignments.py::archive](../../backend/app/api/v1/classroom_assignments.py) |
| POST | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/restore` | [classroom_assignments.py::restore](../../backend/app/api/v1/classroom_assignments.py) |
| POST | `/api/v1/classroom-assignments/{assignment_id}/start` | [classroom_assignments.py::start](../../backend/app/api/v1/classroom_assignments.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/results` | [classroom_assignments.py::results](../../backend/app/api/v1/classroom_assignments.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/students/{student_id}/attempts` | [classroom_assignments.py::student_results](../../backend/app/api/v1/classroom_assignments.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/attempts/{attempt_id}` | [classroom_assignments.py::result_detail](../../backend/app/api/v1/classroom_assignments.py) |
| PUT | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/attempts/{attempt_id}/writing-scores/{writing_task_id}` | [classroom_assignments.py::grade_writing](../../backend/app/api/v1/classroom_assignments.py) |
| PUT | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/attempts/{attempt_id}/speaking-score` | [classroom_assignments.py::grade_speaking](../../backend/app/api/v1/classroom_assignments.py) |
| DELETE | `/api/v1/classrooms/{classroom_id}/sections/{section_id}` | [classroom_classwork.py::delete_section](../../backend/app/api/v1/classroom_classwork.py) |
| DELETE | `/api/v1/classrooms/{classroom_id}/resources/{resource_id}` | [classroom_classwork.py::delete_resource](../../backend/app/api/v1/classroom_classwork.py) |
| DELETE | `/api/v1/classrooms/{classroom_id}/items/{item_id}` | [classroom_classwork.py::remove_assignment](../../backend/app/api/v1/classroom_classwork.py) |
| GET | `/api/v1/classrooms/{classroom_id}/classwork` | [classroom_classwork.py::classwork](../../backend/app/api/v1/classroom_classwork.py) |
| DELETE | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/classwork` | [classroom_classwork.py::remove_assignment_reference](../../backend/app/api/v1/classroom_classwork.py) |
| GET | `/api/v1/classrooms/{classroom_id}/sections` | [classroom_classwork.py::sections](../../backend/app/api/v1/classroom_classwork.py) |
| POST | `/api/v1/classrooms/{classroom_id}/sections` | [classroom_classwork.py::create_section](../../backend/app/api/v1/classroom_classwork.py) |
| PATCH | `/api/v1/classrooms/{classroom_id}/sections/{section_id}` | [classroom_classwork.py::update_section](../../backend/app/api/v1/classroom_classwork.py) |
| POST | `/api/v1/classrooms/{classroom_id}/sections/reorder` | [classroom_classwork.py::reorder_sections](../../backend/app/api/v1/classroom_classwork.py) |
| GET | `/api/v1/classrooms/{classroom_id}/resources` | [classroom_classwork.py::resources](../../backend/app/api/v1/classroom_classwork.py) |
| POST | `/api/v1/classrooms/{classroom_id}/resources` | [classroom_classwork.py::create_resource](../../backend/app/api/v1/classroom_classwork.py) |
| POST | `/api/v1/classrooms/{classroom_id}/resources/upload` | [classroom_classwork.py::upload_resource](../../backend/app/api/v1/classroom_classwork.py) |
| GET | `/api/v1/classrooms/{classroom_id}/resources/{resource_id}` | [classroom_classwork.py::resource_detail](../../backend/app/api/v1/classroom_classwork.py) |
| PATCH | `/api/v1/classrooms/{classroom_id}/resources/{resource_id}` | [classroom_classwork.py::update_resource](../../backend/app/api/v1/classroom_classwork.py) |
| GET | `/api/v1/classrooms/{classroom_id}/resources/{resource_id}/file` | [classroom_classwork.py::resource_file](../../backend/app/api/v1/classroom_classwork.py) |
| POST | `/api/v1/classrooms/{classroom_id}/items` | [classroom_classwork.py::place_assignment](../../backend/app/api/v1/classroom_classwork.py) |
| POST | `/api/v1/classrooms/{classroom_id}/items/reorder` | [classroom_classwork.py::reorder_items](../../backend/app/api/v1/classroom_classwork.py) |
| GET | `/api/v1/me/learning-goals` | [classroom_learning.py::learning_goals](../../backend/app/api/v1/classroom_learning.py) |
| PUT | `/api/v1/me/learning-goals` | [classroom_learning.py::save_learning_goals](../../backend/app/api/v1/classroom_learning.py) |
| GET | `/api/v1/classrooms/{classroom_id}/analytics` | [classroom_learning.py::analytics](../../backend/app/api/v1/classroom_learning.py) |
| GET | `/api/v1/classrooms/{classroom_id}/students/{student_id}/analytics` | [classroom_learning.py::student_analytics](../../backend/app/api/v1/classroom_learning.py) |
| GET | `/api/v1/classrooms/{classroom_id}/my-progress` | [classroom_learning.py::my_progress](../../backend/app/api/v1/classroom_learning.py) |
| GET | `/api/v1/classrooms/{classroom_id}/my-recommendations` | [classroom_learning.py::my_recommendations](../../backend/app/api/v1/classroom_learning.py) |
| GET | `/api/v1/classrooms/{classroom_id}/learning-plans` | [classroom_learning.py::learning_plans](../../backend/app/api/v1/classroom_learning.py) |
| POST | `/api/v1/classrooms/{classroom_id}/students/{student_id}/learning-plans` | [classroom_learning.py::create_plan](../../backend/app/api/v1/classroom_learning.py) |
| PUT | `/api/v1/classrooms/{classroom_id}/students/{student_id}/learning-plans/{plan_id}` | [classroom_learning.py::update_plan](../../backend/app/api/v1/classroom_learning.py) |
| POST | `/api/v1/classrooms/{classroom_id}/learning-plans/{plan_id}/items/{item_id}/complete-resource` | [classroom_learning.py::complete_resource](../../backend/app/api/v1/classroom_learning.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignment-versions/{version_id}` | [classroom_lms.py::assignment_version](../../backend/app/api/v1/classroom_lms.py) |
| GET | `/api/v1/classrooms/{classroom_id}/assignable-tests` | [classroom_lms.py::assignable_tests](../../backend/app/api/v1/classroom_lms.py) |
| GET | `/api/v1/me/classroom-staff-invitations` | [classroom_lms.py::my_staff](../../backend/app/api/v1/classroom_lms.py) |
| GET | `/api/v1/classrooms/{classroom_id}/staff` | [classroom_lms.py::staff](../../backend/app/api/v1/classroom_lms.py) |
| POST | `/api/v1/classrooms/{classroom_id}/staff` | [classroom_lms.py::invite_staff](../../backend/app/api/v1/classroom_lms.py) |
| PATCH | `/api/v1/classrooms/{classroom_id}/staff/{staff_id}` | [classroom_lms.py::update_staff](../../backend/app/api/v1/classroom_lms.py) |
| DELETE | `/api/v1/classrooms/{classroom_id}/staff/{staff_id}` | [classroom_lms.py::revoke_staff](../../backend/app/api/v1/classroom_lms.py) |
| POST | `/api/v1/classrooms/{classroom_id}/staff/{staff_id}/{action}` | [classroom_lms.py::respond_staff](../../backend/app/api/v1/classroom_lms.py) |
| GET | `/api/v1/classrooms/{classroom_id}/gradebook` | [classroom_lms.py::gradebook](../../backend/app/api/v1/classroom_lms.py) |
| GET | `/api/v1/classrooms/{classroom_id}/gradebook/export` | [classroom_lms.py::export_gradebook](../../backend/app/api/v1/classroom_lms.py) |
| PATCH | `/api/v1/classrooms/{classroom_id}/assignments/{assignment_id}/grade-policy` | [classroom_lms.py::grade_policy](../../backend/app/api/v1/classroom_lms.py) |
| GET | `/api/v1/classrooms/{classroom_id}/students/{student_id}/academic-profile` | [classroom_lms.py::academic_profile](../../backend/app/api/v1/classroom_lms.py) |
| DELETE | `/api/v1/classrooms/{classroom_id}/posts/{post_id}` | [classroom_posts.py::delete_post](../../backend/app/api/v1/classroom_posts.py) |
| GET | `/api/v1/classrooms/{classroom_id}/feed` | [classroom_posts.py::feed](../../backend/app/api/v1/classroom_posts.py) |
| POST | `/api/v1/classrooms/{classroom_id}/posts` | [classroom_posts.py::create_post](../../backend/app/api/v1/classroom_posts.py) |
| GET | `/api/v1/classrooms/{classroom_id}/posts/{post_id}` | [classroom_posts.py::post_detail](../../backend/app/api/v1/classroom_posts.py) |
| PATCH | `/api/v1/classrooms/{classroom_id}/posts/{post_id}` | [classroom_posts.py::update_post](../../backend/app/api/v1/classroom_posts.py) |
| POST | `/api/v1/classrooms/{classroom_id}/posts/{post_id}/publish` | [classroom_posts.py::publish_post](../../backend/app/api/v1/classroom_posts.py) |
| POST | `/api/v1/classrooms/{classroom_id}/posts/{post_id}/archive` | [classroom_posts.py::archive_post](../../backend/app/api/v1/classroom_posts.py) |
| POST | `/api/v1/classrooms/{classroom_id}/posts/{post_id}/pin` | [classroom_posts.py::pin_post](../../backend/app/api/v1/classroom_posts.py) |
| GET | `/api/v1/classrooms/{classroom_id}/posts/{post_id}/comments` | [classroom_posts.py::comments](../../backend/app/api/v1/classroom_posts.py) |
| POST | `/api/v1/classrooms/{classroom_id}/posts/{post_id}/comments` | [classroom_posts.py::create_comment](../../backend/app/api/v1/classroom_posts.py) |
| PATCH | `/api/v1/classrooms/{classroom_id}/comments/{comment_id}` | [classroom_posts.py::update_comment](../../backend/app/api/v1/classroom_posts.py) |
| DELETE | `/api/v1/classrooms/{classroom_id}/comments/{comment_id}` | [classroom_posts.py::delete_comment](../../backend/app/api/v1/classroom_posts.py) |
| GET | `/api/v1/classrooms` | [classrooms.py::list_classrooms](../../backend/app/api/v1/classrooms.py) |
| POST | `/api/v1/classrooms` | [classrooms.py::create_classroom](../../backend/app/api/v1/classrooms.py) |
| GET | `/api/v1/classrooms/{classroom_id}` | [classrooms.py::classroom_detail](../../backend/app/api/v1/classrooms.py) |
| PATCH | `/api/v1/classrooms/{classroom_id}` | [classrooms.py::update_classroom](../../backend/app/api/v1/classrooms.py) |
| POST | `/api/v1/classrooms/{classroom_id}/archive` | [classrooms.py::archive_classroom](../../backend/app/api/v1/classrooms.py) |
| POST | `/api/v1/classrooms/{classroom_id}/restore` | [classrooms.py::restore_classroom](../../backend/app/api/v1/classrooms.py) |
| GET | `/api/v1/classrooms/{classroom_id}/members` | [classrooms.py::members](../../backend/app/api/v1/classrooms.py) |
| POST | `/api/v1/classrooms/{classroom_id}/members/{user_id}/remove` | [classrooms.py::remove_member](../../backend/app/api/v1/classrooms.py) |
| POST | `/api/v1/classrooms/{classroom_id}/leave` | [classrooms.py::leave](../../backend/app/api/v1/classrooms.py) |
| GET | `/api/v1/classrooms/{classroom_id}/invitations` | [classrooms.py::invitations](../../backend/app/api/v1/classrooms.py) |
| POST | `/api/v1/classrooms/{classroom_id}/invitations` | [classrooms.py::invite](../../backend/app/api/v1/classrooms.py) |
| GET | `/api/v1/me/classroom-invitations` | [classrooms.py::my_invitations](../../backend/app/api/v1/classrooms.py) |
| POST | `/api/v1/classroom-invitations/{invitation_id}/cancel` | [classrooms.py::cancel_invitation](../../backend/app/api/v1/classrooms.py) |
| POST | `/api/v1/classroom-invitations/{invitation_id}/accept` | [classrooms.py::accept_invitation](../../backend/app/api/v1/classrooms.py) |
| POST | `/api/v1/classroom-invitations/{invitation_id}/decline` | [classrooms.py::decline_invitation](../../backend/app/api/v1/classrooms.py) |
| POST | `/api/v1/test-versions/{version_id}/moderation-requests` | [content_governance.py::submit](../../backend/app/api/v1/content_governance.py) |
| GET | `/api/v1/test-versions/{version_id}/moderation-requests` | [content_governance.py::version_requests](../../backend/app/api/v1/content_governance.py) |
| POST | `/api/v1/test-moderation-requests/{request_id}/cancel` | [content_governance.py::cancel](../../backend/app/api/v1/content_governance.py) |
| GET | `/api/v1/admin/test-moderation-requests` | [content_governance.py::queue](../../backend/app/api/v1/content_governance.py) |
| GET | `/api/v1/admin/test-moderation-requests/{request_id}` | [content_governance.py::detail](../../backend/app/api/v1/content_governance.py) |
| POST | `/api/v1/admin/test-moderation-requests/{request_id}/approve` | [content_governance.py::approve](../../backend/app/api/v1/content_governance.py) |
| POST | `/api/v1/admin/test-moderation-requests/{request_id}/reject` | [content_governance.py::reject](../../backend/app/api/v1/content_governance.py) |
| POST | `/api/v1/admin/test-moderation-requests/{request_id}/revoke` | [content_governance.py::revoke](../../backend/app/api/v1/content_governance.py) |
| GET | `/api/v1/health` | [health.py::health](../../backend/app/api/v1/health.py) |
| GET | `/api/v1/ready` | [health.py::ready](../../backend/app/api/v1/health.py) |
| GET | `/api/v1/history` | [history.py::history](../../backend/app/api/v1/history.py) |
| DELETE | `/api/v1/history/test-versions/{test_version_id}/standalone-attempts` | [history.py::delete_standalone_history](../../backend/app/api/v1/history.py) |
| POST | `/api/v1/test-versions/{version_id}/listening/parts` | [listening.py::create_listening_part](../../backend/app/api/v1/listening.py) |
| PUT | `/api/v1/listening/parts/{part_id}` | [listening.py::update_listening_part](../../backend/app/api/v1/listening.py) |
| DELETE | `/api/v1/listening/parts/{part_id}` | [listening.py::delete_listening_part](../../backend/app/api/v1/listening.py) |
| PUT | `/api/v1/listening/modules/{module_id}/audio` | [listening.py::attach_listening_audio](../../backend/app/api/v1/listening.py) |
| POST | `/api/v1/listening/parts/{part_id}/question-groups` | [listening.py::create_listening_group](../../backend/app/api/v1/listening.py) |
| PUT | `/api/v1/listening/question-groups/{group_id}` | [listening.py::update_listening_group](../../backend/app/api/v1/listening.py) |
| GET | `/api/v1/notifications` | [notifications.py::list_notifications](../../backend/app/api/v1/notifications.py) |
| GET | `/api/v1/notifications/unread-count` | [notifications.py::unread_count](../../backend/app/api/v1/notifications.py) |
| POST | `/api/v1/notifications/read-all` | [notifications.py::mark_all_read](../../backend/app/api/v1/notifications.py) |
| POST | `/api/v1/notifications/{notification_id}/read` | [notifications.py::mark_read](../../backend/app/api/v1/notifications.py) |
| GET | `/api/v1/me/preferences` | [preferences.py::get_preferences](../../backend/app/api/v1/preferences.py) |
| PATCH | `/api/v1/me/preferences` | [preferences.py::update_preferences](../../backend/app/api/v1/preferences.py) |
| GET | `/api/v1/test-versions/{version_id}/builder` | [reading.py::get_builder_version](../../backend/app/api/v1/reading.py) |
| POST | `/api/v1/test-versions/{version_id}/modules` | [reading.py::create_module](../../backend/app/api/v1/reading.py) |
| PATCH | `/api/v1/test-modules/{module_id}` | [reading.py::update_module](../../backend/app/api/v1/reading.py) |
| POST | `/api/v1/test-versions/{version_id}/reading/passages` | [reading.py::create_passage](../../backend/app/api/v1/reading.py) |
| PUT | `/api/v1/reading/passages/{passage_id}` | [reading.py::update_passage](../../backend/app/api/v1/reading.py) |
| DELETE | `/api/v1/reading/passages/{passage_id}` | [reading.py::delete_passage](../../backend/app/api/v1/reading.py) |
| POST | `/api/v1/reading/passages/{passage_id}/question-groups` | [reading.py::create_question_group](../../backend/app/api/v1/reading.py) |
| PUT | `/api/v1/question-groups/{group_id}` | [reading.py::update_question_group](../../backend/app/api/v1/reading.py) |
| DELETE | `/api/v1/question-groups/{group_id}` | [reading.py::delete_question_group](../../backend/app/api/v1/reading.py) |
| PUT | `/api/v1/test-modules/{module_id}/question-groups/order` | [reading.py::reorder_question_groups](../../backend/app/api/v1/reading.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/transcript-runs` | [speaking.py::create_transcript_run](../../backend/app/api/v1/speaking.py) |
| GET | `/api/v1/speaking-attempts/{attempt_id}/transcript-runs` | [speaking.py::latest_transcript_run](../../backend/app/api/v1/speaking.py) |
| GET | `/api/v1/speaking-attempts/{attempt_id}/transcript-runs/{run_id}` | [speaking.py::transcript_run](../../backend/app/api/v1/speaking.py) |
| GET | `/api/v1/speaking-attempts/{attempt_id}/transcript-runs/{run_id}/events` | [speaking.py::transcript_events](../../backend/app/api/v1/speaking.py) |
| GET | `/api/v1/speaking-attempts/{attempt_id}/review` | [speaking.py::speaking_review](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/interrupt` | [speaking.py::interrupt_recording](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/resume` | [speaking.py::resume_recording](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/segments` | [speaking.py::create_segment](../../backend/app/api/v1/speaking.py) |
| PUT | `/api/v1/speaking-attempts/{attempt_id}/segments/{segment_id}/chunks/{sequence}` | [speaking.py::upload_chunk](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/segments/{segment_id}/close` | [speaking.py::close_segment](../../backend/app/api/v1/speaking.py) |
| GET | `/api/v1/speaking-attempts/{attempt_id}/responses/{response_id}/manifest` | [speaking.py::get_manifest](../../backend/app/api/v1/speaking.py) |
| GET | `/api/v1/speaking-attempts/{attempt_id}/segments/{segment_id}/content` | [speaking.py::get_recording](../../backend/app/api/v1/speaking.py) |
| GET | `/api/v1/speaking-attempts/{attempt_id}/state` | [speaking.py::get_state](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/begin` | [speaking.py::begin_prompt](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/select-prompt` | [speaking.py::select_practice_prompt](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/skip-preparation` | [speaking.py::skip_preparation](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/finish-practice` | [speaking.py::finish_free_practice](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/heartbeat` | [speaking.py::heartbeat](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/finish` | [speaking.py::finish_response](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/retry` | [speaking.py::retry_response](../../backend/app/api/v1/speaking.py) |
| PUT | `/api/v1/speaking-attempts/{attempt_id}/notes` | [speaking.py::save_notes](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking/modules/{module_id}/parts` | [speaking.py::create_part](../../backend/app/api/v1/speaking.py) |
| PUT | `/api/v1/speaking/modules/{module_id}/parts/order` | [speaking.py::reorder_parts](../../backend/app/api/v1/speaking.py) |
| PUT | `/api/v1/speaking/parts/{part_id}` | [speaking.py::update_part](../../backend/app/api/v1/speaking.py) |
| DELETE | `/api/v1/speaking/parts/{part_id}` | [speaking.py::delete_part](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking/parts/{part_id}/prompts` | [speaking.py::create_prompt](../../backend/app/api/v1/speaking.py) |
| PUT | `/api/v1/speaking/parts/{part_id}/prompts/order` | [speaking.py::reorder_prompts](../../backend/app/api/v1/speaking.py) |
| DELETE | `/api/v1/speaking/parts/{part_id}/prompts/{prompt_id}` | [speaking.py::delete_prompt](../../backend/app/api/v1/speaking.py) |
| PUT | `/api/v1/speaking/parts/{part_id}/prompts/{prompt_id}` | [speaking.py::update_prompt](../../backend/app/api/v1/speaking.py) |
| PUT | `/api/v1/speaking-attempts/{attempt_id}/final-score` | [speaking.py::save_final_score](../../backend/app/api/v1/speaking.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/ai-runs` | [speaking_ai.py::create_run](../../backend/app/api/v1/speaking_ai.py) |
| GET | `/api/v1/speaking-attempts/{attempt_id}/ai-runs` | [speaking_ai.py::latest_run](../../backend/app/api/v1/speaking_ai.py) |
| GET | `/api/v1/speaking-attempts/{attempt_id}/ai-runs/{run_id}` | [speaking_ai.py::get_run](../../backend/app/api/v1/speaking_ai.py) |
| POST | `/api/v1/speaking-attempts/{attempt_id}/ai-runs/{run_id}/cancel` | [speaking_ai.py::cancel_run](../../backend/app/api/v1/speaking_ai.py) |
| GET | `/api/v1/speaking-attempts/{attempt_id}/ai-runs/{run_id}/events` | [speaking_ai.py::events](../../backend/app/api/v1/speaking_ai.py) |
| POST | `/api/v1/test-sessions` | [test_sessions.py::start_test_session](../../backend/app/api/v1/test_sessions.py) |
| GET | `/api/v1/test-sessions/{session_id}` | [test_sessions.py::get_test_session](../../backend/app/api/v1/test_sessions.py) |
| DELETE | `/api/v1/test-sessions/{session_id}` | [test_sessions.py::delete_test_session](../../backend/app/api/v1/test_sessions.py) |
| POST | `/api/v1/test-sessions/{session_id}/advance` | [test_sessions.py::advance_test_session](../../backend/app/api/v1/test_sessions.py) |
| GET | `/api/v1/tests` | [tests.py::list_tests](../../backend/app/api/v1/tests.py) |
| POST | `/api/v1/tests` | [tests.py::create_test](../../backend/app/api/v1/tests.py) |
| GET | `/api/v1/tests/{test_id}` | [tests.py::get_test](../../backend/app/api/v1/tests.py) |
| POST | `/api/v1/tests/{test_id}/cover` | [tests.py::upload_cover](../../backend/app/api/v1/tests.py) |
| DELETE | `/api/v1/tests/{test_id}/cover` | [tests.py::remove_cover](../../backend/app/api/v1/tests.py) |
| GET | `/api/v1/tests/{test_id}/cover/{cover_id}/content` | [tests.py::get_cover](../../backend/app/api/v1/tests.py) |
| PATCH | `/api/v1/tests/{test_id}` | [tests.py::update_test](../../backend/app/api/v1/tests.py) |
| DELETE | `/api/v1/tests/{test_id}` | [tests.py::delete_test](../../backend/app/api/v1/tests.py) |
| POST | `/api/v1/tests/{test_id}/restore` | [tests.py::restore_test](../../backend/app/api/v1/tests.py) |
| DELETE | `/api/v1/tests/{test_id}/permanent` | [tests.py::permanently_delete_test](../../backend/app/api/v1/tests.py) |
| DELETE | `/api/v1/test-modules/{module_id}` | [tests.py::delete_module](../../backend/app/api/v1/tests.py) |
| POST | `/api/v1/tests/{test_id}/versions` | [tests.py::create_version](../../backend/app/api/v1/tests.py) |
| DELETE | `/api/v1/tests/{test_id}/versions/{version_id}` | [tests.py::delete_draft](../../backend/app/api/v1/tests.py) |
| GET | `/api/v1/test-versions/{version_id}` | [tests.py::get_version](../../backend/app/api/v1/tests.py) |
| POST | `/api/v1/test-versions/{version_id}/validate` | [tests.py::validate_version](../../backend/app/api/v1/tests.py) |
| POST | `/api/v1/test-versions/{version_id}/publish` | [tests.py::publish_version](../../backend/app/api/v1/tests.py) |
| POST | `/api/v1/transfer/export` | [transfer.py::export_tests](../../backend/app/api/v1/transfer.py) |
| POST | `/api/v1/transfer/import` | [transfer.py::import_tests](../../backend/app/api/v1/transfer.py) |
| PUT | `/api/v1/writing/tasks/{task_id}` | [writing.py::update_writing_task](../../backend/app/api/v1/writing.py) |
| GET | `/api/v1/attempts/{attempt_id}/writing/{writing_task_id}/ai-practice-feedback` | [writing_ai.py::get_practice_feedback](../../backend/app/api/v1/writing_ai.py) |
| PUT | `/api/v1/attempts/{attempt_id}/writing/{writing_task_id}/ai-practice-feedback` | [writing_ai.py::save_practice_feedback](../../backend/app/api/v1/writing_ai.py) |
| POST | `/api/v1/attempts/{attempt_id}/writing/{writing_task_id}/ai-grading-runs` | [writing_ai.py::create_run](../../backend/app/api/v1/writing_ai.py) |
| GET | `/api/v1/attempts/{attempt_id}/writing/{writing_task_id}/ai-grading-runs` | [writing_ai.py::list_runs](../../backend/app/api/v1/writing_ai.py) |
| GET | `/api/v1/ai-writing-grading-runs/{run_id}` | [writing_ai.py::get_run](../../backend/app/api/v1/writing_ai.py) |
| POST | `/api/v1/ai-writing-grading-runs/{run_id}/cancel` | [writing_ai.py::cancel_run](../../backend/app/api/v1/writing_ai.py) |
| GET | `/api/v1/ai-writing-grading-runs/{run_id}/events` | [writing_ai.py::stream_events](../../backend/app/api/v1/writing_ai.py) |
| GET | `/api/v1/admin/writing-benchmark/summary` | [writing_benchmark.py::summary](../../backend/app/api/v1/writing_benchmark.py) |
| GET | `/api/v1/admin/writing-benchmark/export` | [writing_benchmark.py::export](../../backend/app/api/v1/writing_benchmark.py) |
| GET | `/api/v1/admin/writing-benchmark/samples` | [writing_benchmark.py::samples](../../backend/app/api/v1/writing_benchmark.py) |
| POST | `/api/v1/admin/writing-benchmark/samples` | [writing_benchmark.py::create_sample](../../backend/app/api/v1/writing_benchmark.py) |
| GET | `/api/v1/admin/writing-benchmark/samples/{sample_id}` | [writing_benchmark.py::detail](../../backend/app/api/v1/writing_benchmark.py) |
| PATCH | `/api/v1/admin/writing-benchmark/samples/{sample_id}` | [writing_benchmark.py::patch_sample](../../backend/app/api/v1/writing_benchmark.py) |
| POST | `/api/v1/admin/writing-benchmark/samples/{sample_id}/complete` | [writing_benchmark.py::complete](../../backend/app/api/v1/writing_benchmark.py) |
| DELETE | `/api/v1/admin/writing-benchmark/samples/{sample_id}` | [writing_benchmark.py::delete_sample](../../backend/app/api/v1/writing_benchmark.py) |
| POST | `/api/v1/admin/writing-benchmark/samples/{sample_id}/image` | [writing_benchmark.py::upload_image](../../backend/app/api/v1/writing_benchmark.py) |
| GET | `/api/v1/admin/writing-benchmark/samples/{sample_id}/image` | [writing_benchmark.py::image](../../backend/app/api/v1/writing_benchmark.py) |
| DELETE | `/api/v1/admin/writing-benchmark/samples/{sample_id}/image` | [writing_benchmark.py::remove_image](../../backend/app/api/v1/writing_benchmark.py) |

## SQLAlchemy entities

Quan hệ/constraints xem file gốc và [data guide](data-architecture.md); bảng sau không thay schema migration.

| Model | Table | Source |
| --- | --- | --- |
| `ClassroomAssignmentExtension` | `classroom_assignment_extensions` | [assignment_scheduling.py](../../backend/app/models/assignment_scheduling.py) |
| `AssignmentPolicyEvent` | `classroom_assignment_policy_events` | [assignment_scheduling.py](../../backend/app/models/assignment_scheduling.py) |
| `Classroom` | `classrooms` | [classroom.py](../../backend/app/models/classroom.py) |
| `ClassroomInvitation` | `classroom_invitations` | [classroom.py](../../backend/app/models/classroom.py) |
| `ClassroomMembership` | `classroom_memberships` | [classroom.py](../../backend/app/models/classroom.py) |
| `ClassroomAssignment` | `classroom_assignments` | [classroom.py](../../backend/app/models/classroom.py) |
| `ClassroomSection` | `classroom_sections` | [classroom_classwork.py](../../backend/app/models/classroom_classwork.py) |
| `ClassroomResource` | `classroom_resources` | [classroom_classwork.py](../../backend/app/models/classroom_classwork.py) |
| `ClassroomContentItem` | `classroom_content_items` | [classroom_classwork.py](../../backend/app/models/classroom_classwork.py) |
| `ClassroomLearningPlan` | `classroom_learning_plans` | [classroom_learning.py](../../backend/app/models/classroom_learning.py) |
| `ClassroomLearningPlanItem` | `classroom_learning_plan_items` | [classroom_learning.py](../../backend/app/models/classroom_learning.py) |
| `ClassroomPost` | `classroom_posts` | [classroom_posts.py](../../backend/app/models/classroom_posts.py) |
| `ClassroomPostResource` | `classroom_post_resources` | [classroom_posts.py](../../backend/app/models/classroom_posts.py) |
| `ClassroomComment` | `classroom_comments` | [classroom_posts.py](../../backend/app/models/classroom_posts.py) |
| `ClassroomStaff` | `classroom_staff` | [classroom_staff.py](../../backend/app/models/classroom_staff.py) |
| `ClassroomStaffEvent` | `classroom_staff_events` | [classroom_staff.py](../../backend/app/models/classroom_staff.py) |
| `TestVersionModeration` | `test_version_moderation` | [content_governance.py](../../backend/app/models/content_governance.py) |
| `User` | `users` | [entities.py](../../backend/app/models/entities.py) |
| `OAuthAccount` | `oauth_accounts` | [entities.py](../../backend/app/models/entities.py) |
| `RefreshSession` | `refresh_sessions` | [entities.py](../../backend/app/models/entities.py) |
| `Test` | `tests` | [entities.py](../../backend/app/models/entities.py) |
| `TestCover` | `test_covers` | [entities.py](../../backend/app/models/entities.py) |
| `TestVersion` | `test_versions` | [entities.py](../../backend/app/models/entities.py) |
| `TestModule` | `test_modules` | [entities.py](../../backend/app/models/entities.py) |
| `TestSession` | `test_sessions` | [entities.py](../../backend/app/models/entities.py) |
| `ReadingPassage` | `reading_passages` | [entities.py](../../backend/app/models/entities.py) |
| `ListeningPart` | `listening_parts` | [entities.py](../../backend/app/models/entities.py) |
| `WritingTask` | `writing_tasks` | [entities.py](../../backend/app/models/entities.py) |
| `QuestionGroup` | `question_groups` | [entities.py](../../backend/app/models/entities.py) |
| `Question` | `questions` | [entities.py](../../backend/app/models/entities.py) |
| `Attempt` | `attempts` | [entities.py](../../backend/app/models/entities.py) |
| `AttemptAnswer` | `attempt_answers` | [entities.py](../../backend/app/models/entities.py) |
| `AttemptWritingResponse` | `attempt_writing_responses` | [entities.py](../../backend/app/models/entities.py) |
| `AttemptWritingScore` | `attempt_writing_scores` | [entities.py](../../backend/app/models/entities.py) |
| `Highlight` | `highlights` | [entities.py](../../backend/app/models/entities.py) |
| `QuestionFlag` | `question_flags` | [entities.py](../../backend/app/models/entities.py) |
| `Asset` | `assets` | [entities.py](../../backend/app/models/entities.py) |
| `AttemptEvent` | `attempt_events` | [entities.py](../../backend/app/models/entities.py) |
| `Notification` | `notifications` | [notifications.py](../../backend/app/models/notifications.py) |
| `UserPreference` | `user_preferences` | [preferences.py](../../backend/app/models/preferences.py) |
| `SpeakingPart` | `speaking_parts` | [speaking.py](../../backend/app/models/speaking.py) |
| `SpeakingPrompt` | `speaking_prompts` | [speaking.py](../../backend/app/models/speaking.py) |
| `SpeakingResponse` | `speaking_responses` | [speaking.py](../../backend/app/models/speaking.py) |
| `SpeakingResponseTake` | `speaking_response_takes` | [speaking.py](../../backend/app/models/speaking.py) |
| `SpeakingPromptProgress` | `speaking_prompt_progress` | [speaking.py](../../backend/app/models/speaking.py) |
| `SpeakingAudioSegment` | `speaking_audio_segments` | [speaking.py](../../backend/app/models/speaking.py) |
| `SpeakingAudioChunk` | `speaking_audio_chunks` | [speaking.py](../../backend/app/models/speaking.py) |
| `SpeakingMediaCleanup` | `speaking_media_cleanup` | [speaking.py](../../backend/app/models/speaking.py) |
| `AttemptSpeakingScore` | `attempt_speaking_scores` | [speaking.py](../../backend/app/models/speaking.py) |
| `SpeakingAIGradingRun` | `speaking_ai_grading_runs` | [speaking_ai.py](../../backend/app/models/speaking_ai.py) |
| `SpeakingAIGradingEvent` | `speaking_ai_grading_events` | [speaking_ai.py](../../backend/app/models/speaking_ai.py) |
| `SpeakingNormalizedAudio` | `speaking_normalized_audio` | [speaking_transcript.py](../../backend/app/models/speaking_transcript.py) |
| `SpeakingTranscriptRun` | `speaking_transcript_runs` | [speaking_transcript.py](../../backend/app/models/speaking_transcript.py) |
| `SpeakingTranscriptEvent` | `speaking_transcript_events` | [speaking_transcript.py](../../backend/app/models/speaking_transcript.py) |
| `SpeakingTranscript` | `speaking_transcripts` | [speaking_transcript.py](../../backend/app/models/speaking_transcript.py) |
| `WritingAIGradingRun` | `writing_ai_grading_runs` | [writing_ai.py](../../backend/app/models/writing_ai.py) |
| `WritingAIGradingEvent` | `writing_ai_grading_events` | [writing_ai.py](../../backend/app/models/writing_ai.py) |
| `WritingAIPracticeFeedback` | `writing_ai_practice_feedback` | [writing_ai.py](../../backend/app/models/writing_ai.py) |
| `WritingBenchmarkSample` | `writing_benchmark_samples` | [writing_benchmark.py](../../backend/app/models/writing_benchmark.py) |

## Next App Router pages

Route folder không tự bảo đảm quyền; xem page guards, proxy và backend policy.

- [admin/classrooms/page.tsx](../../frontend/src/app/admin/classrooms/page.tsx)
- [admin/moderation/[requestId]/page.tsx](../../frontend/src/app/admin/moderation/[requestId]/page.tsx)
- [admin/moderation/page.tsx](../../frontend/src/app/admin/moderation/page.tsx)
- [admin/page.tsx](../../frontend/src/app/admin/page.tsx)
- [admin/tests/[testId]/page.tsx](../../frontend/src/app/admin/tests/[testId]/page.tsx)
- [admin/tests/[testId]/versions/[versionId]/edit/page.tsx](../../frontend/src/app/admin/tests/[testId]/versions/[versionId]/edit/page.tsx)
- [admin/tests/[testId]/versions/[versionId]/preview/page.tsx](../../frontend/src/app/admin/tests/[testId]/versions/[versionId]/preview/page.tsx)
- [admin/tests/new/page.tsx](../../frontend/src/app/admin/tests/new/page.tsx)
- [admin/tests/page.tsx](../../frontend/src/app/admin/tests/page.tsx)
- [admin/users/[userId]/page.tsx](../../frontend/src/app/admin/users/[userId]/page.tsx)
- [admin/writing-benchmark/page.tsx](../../frontend/src/app/admin/writing-benchmark/page.tsx)
- [analytics/page.tsx](../../frontend/src/app/analytics/page.tsx)
- [attempt/[attemptId]/page.tsx](../../frontend/src/app/attempt/[attemptId]/page.tsx)
- [classrooms/[classroomId]/assignments/[assignmentId]/results/[attemptId]/page.tsx](../../frontend/src/app/classrooms/[classroomId]/assignments/[assignmentId]/results/[attemptId]/page.tsx)
- [classrooms/[classroomId]/assignments/[assignmentId]/results/page.tsx](../../frontend/src/app/classrooms/[classroomId]/assignments/[assignmentId]/results/page.tsx)
- [classrooms/[classroomId]/overview/page.tsx](../../frontend/src/app/classrooms/[classroomId]/overview/page.tsx)
- [classrooms/[classroomId]/page.tsx](../../frontend/src/app/classrooms/[classroomId]/page.tsx)
- [classrooms/page.tsx](../../frontend/src/app/classrooms/page.tsx)
- [history/page.tsx](../../frontend/src/app/history/page.tsx)
- [library/[versionId]/page.tsx](../../frontend/src/app/library/[versionId]/page.tsx)
- [library/page.tsx](../../frontend/src/app/library/page.tsx)
- [login/page.tsx](../../frontend/src/app/login/page.tsx)
- [page.tsx](../../frontend/src/app/page.tsx)
- [practice/page.tsx](../../frontend/src/app/practice/page.tsx)
- [profile/page.tsx](../../frontend/src/app/profile/page.tsx)
- [register/page.tsx](../../frontend/src/app/register/page.tsx)
- [review/[attemptId]/page.tsx](../../frontend/src/app/review/[attemptId]/page.tsx)
- [session/restore/page.tsx](../../frontend/src/app/session/restore/page.tsx)
- [settings/personalization/page.tsx](../../frontend/src/app/settings/personalization/page.tsx)
- [teacher/classrooms/[classroomId]/assignments/[assignmentId]/results/[attemptId]/page.tsx](../../frontend/src/app/teacher/classrooms/[classroomId]/assignments/[assignmentId]/results/[attemptId]/page.tsx)
- [teacher/classrooms/[classroomId]/assignments/[assignmentId]/results/page.tsx](../../frontend/src/app/teacher/classrooms/[classroomId]/assignments/[assignmentId]/results/page.tsx)
- [teacher/classrooms/[classroomId]/overview/page.tsx](../../frontend/src/app/teacher/classrooms/[classroomId]/overview/page.tsx)
- [teacher/classrooms/[classroomId]/page.tsx](../../frontend/src/app/teacher/classrooms/[classroomId]/page.tsx)
- [teacher/classrooms/page.tsx](../../frontend/src/app/teacher/classrooms/page.tsx)
- [teacher/tests/[testId]/versions/[versionId]/edit/page.tsx](../../frontend/src/app/teacher/tests/[testId]/versions/[versionId]/edit/page.tsx)
- [teacher/tests/[testId]/versions/[versionId]/preview/page.tsx](../../frontend/src/app/teacher/tests/[testId]/versions/[versionId]/preview/page.tsx)
- [teacher/tests/new/page.tsx](../../frontend/src/app/teacher/tests/new/page.tsx)
- [teacher/tests/page.tsx](../../frontend/src/app/teacher/tests/page.tsx)
- [test-session/[sessionId]/page.tsx](../../frontend/src/app/test-session/[sessionId]/page.tsx)
- [transfer/page.tsx](../../frontend/src/app/transfer/page.tsx)

## Giới hạn và maintenance

Source map có 242 khai báo API và 59 mapped entities. Mỗi module guide chọn relevant tests/services; không phải tuyên bố mọi dòng code đã review. Khi đổi route/model/page, regenerate hoặc sửa bảng này và kiểm source paths. [Module catalog](module-catalog.md), [coverage](../DOCUMENTATION_COVERAGE.md).
