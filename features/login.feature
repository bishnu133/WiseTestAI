@smoke1 @critical
Feature: User Login
  As a customer
  I want to log into my account
  So that I can access User's personal information

  Background:
    Given I navigate to the login page

  @smoke1
  Scenario: Successful login with valid credentials
    When I enter "bishnu_username" in the "Username" field
    And I enter "Password" in the "Password" field
    And I click the "Sign In" button
    And I click on "Customer Care"
    Then I select "Participant" in search type dropdown
    When I search with text "XXXXXX"
    Then the table should show:
      | Account Status | Profile Status |
      | Active         | Verified       |
    When I click on the PPHID link "XXXXXXX"
    Then I verify text "Participant"

#    Then I should see "Welcome back!"
#    And I should see the "My Account" link

#  @negative
#  Scenario: Login fails with invalid password
#    When I enter "testuser@example.com" in the "email" field
#    And I enter "wrongpassword" in the "password" field
#    And I click the "Sign In" button
#    Then I should see "Invalid email or password"
#
#  @data_driven
#  Scenario Outline: Login with different user types
#    When I enter "<email>" in the "email" field
#    And I enter "<password>" in the "password" field
#    And I click the "Sign In" button
#    Then I should see "<message>"
#
#    Examples:
#      | email                  | password    | message         |
#      | admin@example.com      | Admin@123   | Admin Dashboard |
#      | customer@example.com   | Cust@123    | Welcome back!   |
#      | vendor@example.com     | Vendor@123  | Vendor Portal   |
