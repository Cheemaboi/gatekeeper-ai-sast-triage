package org.owasp.benchmark.testcode;
public class BenchmarkTest00001 {
  public void doPost(javax.servlet.http.HttpServletRequest request) throws Exception {
    String param = request.getParameter("id");
    String sql = "SELECT * FROM USERS WHERE ID='" + param + "'";
    java.sql.Statement st = org.owasp.benchmark.helpers.DatabaseHelper.getSqlStatement();
    // flagged line below
    st.execute(sql);
  }
}
